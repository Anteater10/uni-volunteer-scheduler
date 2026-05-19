// Geometry helpers for the architecture diagram.
// Pure functions only — keep this side-effect free so it's trivial to test.

export const NODE_W = 240;
export const NODE_H = 56;
export const COL_GAP = 96;
export const ROW_HEIGHT = 76;
export const PAD_X = 32;
export const PAD_Y = 32;

export function nodePosition(node) {
  // col is 1-indexed; we keep 0-indexed math
  const x = PAD_X + (node.col - 1) * (NODE_W + COL_GAP);
  const y = PAD_Y + node.row * ROW_HEIGHT;
  return { x, y, w: NODE_W, h: NODE_H };
}

export function diagramSize(nodes) {
  let maxCol = 1;
  let maxRow = 0;
  for (const n of nodes) {
    if (n.col > maxCol) maxCol = n.col;
    if (n.row > maxRow) maxRow = n.row;
  }
  const width = PAD_X * 2 + maxCol * (NODE_W + COL_GAP) - COL_GAP;
  const height = PAD_Y * 2 + (maxRow + 1) * ROW_HEIGHT + 24;
  return { width, height };
}

// Compute curved-Bezier connector endpoints for an edge.
// Returns {path, midX, midY} suitable for <path d={path}> and step badge placement.
export function curvedConnector(fromNode, toNode) {
  const a = nodePosition(fromNode);
  const b = nodePosition(toNode);

  // Source: right edge of "from" node, vertical mid
  const x1 = a.x + a.w;
  const y1 = a.y + a.h / 2;
  // Target: left edge of "to" node, vertical mid
  const x2 = b.x;
  const y2 = b.y + b.h / 2;

  // If target is to the LEFT of source (back-edge), route around the bottom
  // by flipping start/end horizontally to keep the curve readable.
  const goingRight = x2 > x1;
  const startX = goingRight ? x1 : a.x;
  const startY = y1;
  const endX = goingRight ? x2 : b.x + b.w;
  const endY = y2;

  const dx = endX - startX;
  const flex = Math.max(60, Math.abs(dx) * 0.5);

  const cp1x = startX + (goingRight ? flex : -flex);
  const cp1y = startY;
  const cp2x = endX + (goingRight ? -flex : flex);
  const cp2y = endY;

  const path = `M ${startX} ${startY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${endX} ${endY}`;

  // Midpoint of cubic Bezier at t=0.5
  const midX =
    0.125 * startX + 0.375 * cp1x + 0.375 * cp2x + 0.125 * endX;
  const midY =
    0.125 * startY + 0.375 * cp1y + 0.375 * cp2y + 0.125 * endY;

  return { path, midX, midY, startX, startY, endX, endY };
}
