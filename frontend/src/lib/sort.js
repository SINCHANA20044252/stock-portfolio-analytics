// Sort rows by a getter; null/undefined always go last whatever the direction.
export function sortRows(rows, get, dir = 1) {
  return [...rows].sort((a, b) => {
    const x = get(a), y = get(b)
    if (x == null && y == null) return 0
    if (x == null) return 1
    if (y == null) return -1
    return (x > y ? 1 : x < y ? -1 : 0) * dir
  })
}

export function nextSort(current, key) {
  return current.key === key ? { key, dir: -current.dir } : { key, dir: 1 }
}
