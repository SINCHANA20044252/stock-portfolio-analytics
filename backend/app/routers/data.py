import json
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ImportBatch, Transaction, User
from ..schemas import ImportConfirm
from ..security import get_current_user
from ..services import exporter, importer, portfolio
from .common import audit, check_ledger, public

router = APIRouter(prefix="/data", tags=["import / export"])
BATCH_TTL = timedelta(hours=1)


@router.get("/template.csv")
def template():
    return Response(importer.TEMPLATE_CSV, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="transactions-template.csv"'})


@router.post("/import/preview")
def preview(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = file.file.read(importer.MAX_BYTES + 1)
    try:
        df = importer.parse_file(file.filename or "", content)
    except importer.ImportFileError as exc:
        raise HTTPException(400, str(exc)) from exc
    result = importer.validate(df, portfolio.load_transactions(db, user.id))
    batch = ImportBatch(id=str(uuid.uuid4()), user_id=user.id, filename=(file.filename or "upload")[:255],
                        records_json=df.to_json(orient="records", date_format="iso"))
    db.add(batch)
    audit(db, user.id, "import_preview", f"{batch.filename}: {result['summary']}")
    db.commit()
    return {"import_id": batch.id, "filename": batch.filename, **result}


def _batch(db: Session, user: User, import_id: str) -> ImportBatch:
    b = db.query(ImportBatch).filter(ImportBatch.id == import_id, ImportBatch.user_id == user.id).first()
    if not b or b.status != "pending":
        raise HTTPException(404, "Import not found or already finished")
    created = b.created_at if b.created_at.tzinfo else b.created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > BATCH_TTL:
        raise HTTPException(410, "This import preview expired. Upload the file again.")
    return b


@router.post("/import/{import_id}/confirm")
def confirm(import_id: str, body: ImportConfirm, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = _batch(db, user, import_id)
    existing = portfolio.load_transactions(db, user.id)
    # Validate again now: your data may have changed since the preview.
    result = importer.validate(pd.DataFrame(json.loads(b.records_json)), existing)
    s = result["summary"]
    if s["errors"] and not body.import_valid_only:
        raise HTTPException(400, f"{s['errors']} row(s) have errors. Fix the file, or confirm with import_valid_only=true to import only the {s['valid']} valid row(s).")
    good = [r for r in result["rows"] if r["status"] == "valid"]
    if not good:
        raise HTTPException(400, "There are no valid rows to import.")
    new = [{**r["data"], "id": f"imp-{i}", "date": datetime.fromisoformat(r["data"]["date"]).date(), "company_name": r["data"]["company_name"] or ""} for i, r in enumerate(good)]
    check_ledger(existing + new)
    for r in good:
        d = r["data"]
        db.add(Transaction(user_id=user.id, symbol=d["symbol"], company_name=d["company_name"], type=d["type"], quantity=d["quantity"],
                           price=d["price"], fees=d["fees"] or 0.0, trade_date=datetime.fromisoformat(d["date"]).date(),
                           note=f"Imported from {b.filename}"[:255], source="import"))
        portfolio.ensure_position(db, user.id, d["symbol"], d["company_name"], d["sector"], price_hint=d["price"])
    b.status = "confirmed"
    b.records_json = "[]"  # no need to keep the uploaded data
    audit(db, user.id, "import_confirm", f"{len(good)} transactions from {b.filename}")
    db.commit()
    return {"imported": len(good), "skipped_duplicates": s["duplicates"], "skipped_errors": s["errors"]}


@router.delete("/import/{import_id}", status_code=204)
def cancel(import_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = _batch(db, user, import_id)
    b.status, b.records_json = "cancelled", "[]"
    audit(db, user.id, "import_cancel", b.filename)
    db.commit()


# ---------- exports ----------
def _download(content: bytes, media: str, name: str) -> Response:
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/export/holdings.csv")
def export_holdings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    val = portfolio.valuation(db, user.id)
    return _download(exporter.to_csv(val["holdings"], exporter.HOLDING_COLS), "text/csv", "holdings.csv")


@router.get("/export/transactions.csv")
def export_transactions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _download(exporter.to_csv(portfolio.load_transactions(db, user.id), exporter.TXN_COLS), "text/csv", "transactions.csv")


@router.get("/export/pnl.csv")
def export_pnl(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    val = portfolio.valuation(db, user.id)
    rows = exporter.pnl_rows(val["holdings"], val["closed"])
    return _download(exporter.to_csv(rows, ["symbol", "status", "invested", "market_value", "unrealized_pnl", "realized_pnl"]), "text/csv", "profit-and-loss.csv")


@router.get("/export/analytics.csv")
def export_analytics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    perf = portfolio.performance_bundle(db, user.id, "ALL")
    cols = ["date", "value", "invested", "pnl", "daily_return_pct", "cumulative_return_pct", "estimated"]
    return _download(exporter.to_csv(perf["series"], cols), "text/csv", "portfolio-analytics.csv")


@router.get("/export/report.xlsx")
def export_report(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    val = portfolio.valuation(db, user.id)
    perf = portfolio.performance_bundle(db, user.id, "ALL", val["transactions"])
    risk = portfolio.risk_bundle(db, user.id, val, perf)
    content = exporter.to_excel(
        holdings=val["holdings"], transactions=val["transactions"], totals=public(val)["totals"], performance=perf["summary"], risk=risk,
        series=perf["series"], monthly=perf["monthly"], closed=val["closed"])
    return _download(content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "portfolio-report.xlsx")
