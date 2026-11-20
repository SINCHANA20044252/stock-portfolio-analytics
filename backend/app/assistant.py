"""'Ask AI' assistant: portfolio-aware retrieval (RAG) over the user's own metrics plus a finance glossary.

Retrieval is TF-IDF cosine similarity (no external service needed). If GEMINI_API_KEY is set,
the retrieved passages are sent to Gemini to write a natural answer; otherwise the best
passages are returned directly. Either way, sources are cited.
"""
import json
import math
import os
import re
import urllib.request
from collections import Counter

KNOWLEDGE_BASE = [
    {"source": "Glossary: Expense ratio", "text": "The expense ratio is the yearly fee a mutual fund charges, shown as a percentage of your investment. A fund with a 1% expense ratio costs 1000 rupees a year per 100000 rupees invested. Lower is usually better, especially for index funds."},
    {"source": "Glossary: SIP", "text": "A Systematic Investment Plan (SIP) invests a fixed amount in a fund every month. It builds discipline and averages out purchase prices over time, which is called rupee cost averaging."},
    {"source": "Glossary: Diversification", "text": "Diversification means spreading money across different companies, sectors and asset types so that one bad investment does not hurt the whole portfolio. Holding stocks from only one sector is concentration risk."},
    {"source": "Glossary: Index fund", "text": "An index fund copies a market index such as the Nifty 50. It has low costs and no fund manager picking stocks. It gives market returns, not more and not less."},
    {"source": "Glossary: Compound growth", "text": "Compounding means you earn returns on your earlier returns. Money invested for a long time grows faster each year. Starting early matters more than investing large amounts later."},
    {"source": "Glossary: Sharpe ratio", "text": "The Sharpe ratio measures return per unit of risk. It is the extra return over a risk-free rate divided by volatility. A higher Sharpe ratio means better risk-adjusted performance."},
    {"source": "Glossary: Volatility", "text": "Volatility shows how much an investment price moves up and down. High volatility means bigger swings and higher risk. Equity is more volatile than debt funds."},
    {"source": "Glossary: Asset allocation", "text": "Asset allocation is how you divide money between equity, debt, gold and cash. Younger investors with long goals often hold more equity. Shorter goals need more stable assets like debt."},
    {"source": "Glossary: Mutual fund NAV", "text": "NAV, or Net Asset Value, is the price of one unit of a mutual fund. It is calculated at the end of each trading day. A low NAV does not mean a fund is cheap."},
    {"source": "Glossary: Maximum drawdown", "text": "Maximum drawdown is the largest fall from a previous peak to a later low, shown as a percentage. If a portfolio rose to 120 and then fell to 90, the drawdown was 25 percent. It shows how painful the worst stretch was, not how likely it is to repeat."},
    {"source": "Glossary: HHI", "text": "The Herfindahl-Hirschman Index (HHI) adds up the squares of each holding's weight in the portfolio. It runs from near 0 to 1. A value of 1 means everything is in one stock. Equal weights across n stocks give 1 divided by n. Lower means more diversified."},
    {"source": "Glossary: Realized and unrealized profit", "text": "Unrealized profit or loss is the gain on shares you still hold, based on today's price. Realized profit or loss is locked in when you sell. Both together are your total profit or loss."},
    {"source": "Glossary: Weighted average cost", "text": "Weighted average cost is your average purchase price per share across all buys, including brokerage. When you sell, the profit is the sale price minus this average. Buying more at a different price changes the average."},
    {"source": "Glossary: Concentration risk", "text": "Concentration risk means a large share of your money sits in one stock or one sector. If that stock or sector falls, the whole portfolio falls with it. Spreading money across more holdings and sectors reduces it, but does not remove market risk."},
    {"source": "Glossary: Annualized return", "text": "Annualized return converts a gain over any period into a yearly rate so different periods can be compared. It is only meaningful for periods of about a year or more, because short gains scaled up to a year are misleading."},
    {"source": "Glossary: Rebalancing", "text": "Rebalancing means adjusting your holdings back to your target allocation, for example selling some of a sector that grew too large. It controls risk and is usually done once or twice a year."},
]

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "is", "of", "to", "and", "in", "it", "for", "what", "how", "does", "do", "i", "my", "me", "are", "on", "or", "that", "this", "with"}


def _tokens(text: str) -> list[str]:
    # crude stemming (first 6 letters) so "diversify" matches "diversification"
    return [t[:6] for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in _STOP]


def _build_index():
    docs = [Counter(_tokens(d["text"] + " " + d["source"])) for d in KNOWLEDGE_BASE]
    n = len(docs)
    df: Counter = Counter()
    for d in docs:
        df.update(d.keys())
    idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
    return docs, idf


_DOCS, _IDF = _build_index()


def _vec(counter: Counter) -> dict[str, float]:
    return {t: c * _IDF.get(t, 1.0) for t, c in counter.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(a[t] * b.get(t, 0.0) for t in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def retrieve(question: str, k: int = 2) -> list[dict]:
    q = _vec(Counter(_tokens(question)))
    scored = [(_cosine(q, _vec(d)), i) for i, d in enumerate(_DOCS)]
    scored.sort(reverse=True)
    return [
        {"source": KNOWLEDGE_BASE[i]["source"], "text": KNOWLEDGE_BASE[i]["text"], "score": round(s, 3)}
        for s, i in scored[:k]
        if s > 0.12
    ]



# ---------------------------------------------------------------------------------------------
# Portfolio-aware answers.
# The assistant never touches the database. The API builds `ctx` from the AUTHENTICATED user's own
# data and passes it in, so there is no code path that can read another user's figures.
# Every number in an answer comes from `ctx`; Gemini (optional) may only rephrase those facts.
# ---------------------------------------------------------------------------------------------

def inr(x) -> str:
    if x is None:
        return "n/a"
    neg = x < 0
    x = abs(round(float(x), 2))
    whole, frac = divmod(round(x * 100), 100)
    s = str(whole)
    if len(s) > 3:
        head_, tail = s[:-3], s[-3:]
        parts = []
        while len(head_) > 2:
            parts.insert(0, head_[-2:])
            head_ = head_[:-2]
        if head_:
            parts.insert(0, head_)
        s = ",".join(parts + [tail])
    out = f"₹{s}" + (f".{frac:02d}" if frac else "")
    return "-" + out if neg else out


def pct(x) -> str:
    return "n/a" if x is None else f"{x:.2f}%"


INTENTS = [
    ("total_value", r"\b(total|current)\b.*\b(portfolio )?value\b|\bhow much\b.*\b(worth|portfolio)\b|\bnet worth\b|\bportfolio value\b"),
    ("top_sector", r"\bsector\b.*\b(highest|largest|biggest|exposure|allocation|most)\b|\b(highest|largest|biggest|most)\b.*\bsector\b|\bsector exposure\b"),
    ("top_stock", r"\b(highest|largest|biggest|top|most)\b.*\b(allocation|weight|stock|holding)\b|\bwhich stock\b.*\ballocation"),
    ("best_return", r"\b(which|what)\b.*\b(stock|holding)\b.*\b(highest|best|top|most)\b.*\b(return|gain|profit|performance)|\bbest[- ]performing\b|\bhighest return\b"),
    ("worst_return", r"\bworst[- ]performing\b|\b(lowest|worst)\b.*\b(return|performance)\b"),
    ("pnl", r"\b(profit|loss|p&l|pnl|gain|returns?)\b.*\b(overall|total|my)\b|\boverall\b.*\b(profit|loss|return)|\bam i (in profit|up|down)\b|\bmy (profit|loss)\b"),
    ("explain_diversification", r"\bdiversif\w*\b.*\b(my|portfolio)\b|\b(my|portfolio)\b.*\bdiversif|\bexplain\b.*\bdiversif"),
    ("explain_concentration", r"\bconcentration\b.*\b(my|portfolio|risk)\b|\brisk\b.*\b(my|portfolio|concentration)\b|\bhow risky\b|\brisk score\b"),
    ("monthly", r"\bmonthly\b.*\b(performance|return|summary)|\bsummari[sz]e\b.*\b(month|performance)|\bperformance\b.*\bmonth"),
]
_COMPILED = [(n, re.compile(p, re.I)) for n, p in INTENTS]


def detect_intent(question: str) -> str | None:
    for name, rx in _COMPILED:
        if rx.search(question):
            return name
    return None


def _no_data(ctx: dict) -> bool:
    return not ctx.get("holdings")


def _facts_answer(intent: str, ctx: dict) -> tuple[str, dict] | None:
    t, hs = ctx.get("totals", {}), ctx.get("holdings", [])
    priced = [h for h in hs if h.get("market_value") is not None]
    if intent == "total_value":
        facts = {"market_value": t.get("market_value"), "total_invested": t.get("total_invested"), "holdings": len(hs)}
        txt = f"Your portfolio is worth {inr(t.get('market_value'))} across {len(hs)} holding(s), based on the latest prices stored in the app."
        if ctx.get("missing_prices"):
            txt += f" These holdings have no price yet and are not counted: {', '.join(ctx['missing_prices'])}."
        return txt, facts
    if intent == "top_stock":
        top = max(priced, key=lambda h: h["market_value"], default=None)
        if not top:
            return None
        return (f"{top['symbol']} has the highest allocation: {top['weight']:.1f}% of your portfolio ({inr(top['market_value'])}).",
                {"symbol": top["symbol"], "weight_pct": top["weight"], "market_value": top["market_value"]})
    if intent == "top_sector":
        sec = ctx.get("sectors", [])
        if not sec:
            return None
        s0 = sec[0]
        rest = ", ".join(f"{s['sector']} {s['percent']:.1f}%" for s in sec[1:4])
        return (f"{s0['sector']} is your largest sector at {s0['percent']:.1f}% ({inr(s0['value'])})." + (f" Next: {rest}." if rest else ""),
                {"sector": s0["sector"], "percent": s0["percent"]})
    if intent in ("best_return", "worst_return"):
        pick = (ctx.get("best") if intent == "best_return" else ctx.get("worst"))
        if not pick:
            return None
        word = "highest" if intent == "best_return" else "lowest"
        return (f"{pick['symbol']} has the {word} return among stocks you hold: {pct(pick['pct'])} on your average cost (unrealized, before any sale).",
                {"symbol": pick["symbol"], "unrealized_pct": pick["pct"]})
    if intent == "pnl":
        facts = {k: t.get(k) for k in ("unrealized_pnl", "realized_pnl", "total_pnl", "overall_return_pct")}
        return (f"Your total profit/loss is {inr(t.get('total_pnl'))} ({pct(t.get('overall_return_pct'))} of everything you invested). "
                f"Unrealized (shares you still hold): {inr(t.get('unrealized_pnl'))}. Realized (from sales): {inr(t.get('realized_pnl'))}.", facts)
    r = ctx.get("risk") or {}
    c = r.get("concentration") or {}
    if intent == "explain_diversification":
        if not c.get("has_data"):
            return None
        txt = (f"Your diversification score is {r['diversification_score']}/100. You hold {c['n']} stocks in {len(c['sector_weights'])} sector(s); "
               f"HHI is {c['hhi']:.2f}, roughly equal to {c['effective_holdings']:.1f} equally sized holdings. "
               f"The largest stock is {c['top_stock']} ({c['top_stock_pct']:.1f}%) and the largest sector is {c['top_sector']} ({c['top_sector_pct']:.1f}%).")
        return txt, {"diversification_score": r["diversification_score"], "hhi": c["hhi"], "n": c["n"]}
    if intent == "explain_concentration":
        if not c.get("has_data"):
            return None
        warn = " ".join(r.get("warnings") or []) or "No concentration limit (40% per stock, 50% per sector) is breached."
        return (f"Risk category: {r['risk_category']} (score {r['risk_score']}/100, higher is riskier). {warn} "
                f"This score mainly reflects how spread out your money is. It is not a full measure of investment risk.",
                {"risk_score": r["risk_score"], "category": r["risk_category"], "warnings": r.get("warnings")})
    if intent == "monthly":
        m = ctx.get("monthly") or []
        if not m:
            return ("There is no monthly performance yet. It needs stored price history: open Market data and refresh prices.", {})
        last = m[-6:]
        best = max(m, key=lambda x: x["return_pct"])
        worst = min(m, key=lambda x: x["return_pct"])
        lines = "; ".join(f"{x['period']}: {x['return_pct']:+.2f}%" for x in last)
        return (f"Recent monthly returns (time-weighted): {lines}. Best month: {best['period']} ({best['return_pct']:+.2f}%). "
                f"Worst month: {worst['period']} ({worst['return_pct']:+.2f}%).", {"months": last})
    return None


def _ask_gemini(question: str, passages: list[dict], facts: dict | None = None) -> str | None:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    context = "\n".join(f"- {p['text']}" for p in passages)
    facts_txt = json.dumps(facts, default=str) if facts else "none"
    prompt = (
        "You are a careful investing explainer inside a portfolio tracker. Use ONLY the glossary context and the portfolio facts "
        "below. Never invent or estimate any number; quote portfolio numbers exactly as given. If the facts do not contain what is "
        "needed, say so. Keep it short and simple. This is education, not investment advice, and never promise returns.\n\n"
        f"Glossary context:\n{context or 'none'}\n\nPortfolio facts (JSON, from this user's own data):\n{facts_txt}\n\nQuestion: {question}"
    )
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None  # fall back to the grounded plain answer if the API fails


OUT_OF_SCOPE = ("I can help with your portfolio (value, allocation, sectors, returns, risk, monthly performance) and with investing terms such as "
                "SIP, expense ratio, diversification, drawdown or HHI. I can't answer that one. Try one of those topics.")


def answer(question: str, ctx: dict | None = None) -> dict:
    """ctx = the signed-in user's own metrics (see routers/assistant.py). None means glossary-only."""
    ctx = ctx or {}
    intent = detect_intent(question)
    passages = retrieve(question)
    grounded: tuple[str, dict] | None = None
    if intent:
        if _no_data(ctx):
            return {"answer": "You have no holdings yet, so I have no figures to talk about. Add a transaction first, then ask again.",
                    "sources": [], "grounded": False, "intent": intent, "used_ai": False}
        grounded = _facts_answer(intent, ctx)
        if grounded and intent in ("explain_diversification", "explain_concentration"):
            passages = retrieve("diversification concentration HHI " + question, k=2) or passages
    if grounded is None and not passages:
        return {"answer": OUT_OF_SCOPE, "sources": [], "grounded": False, "intent": intent, "used_ai": False}

    sources = ["Your portfolio data"] if grounded else []
    sources += [p["source"] for p in passages]
    text, facts = grounded if grounded else (passages[0]["text"], None)
    ai_text = _ask_gemini(question, passages, facts)
    out = {"answer": ai_text or text, "sources": sources, "grounded": bool(grounded), "intent": intent, "used_ai": bool(ai_text)}
    if facts:
        out["facts"] = facts
        if ai_text:
            out["plain_answer"] = text  # the exact computed answer, shown so the AI wording can be checked
    return out
