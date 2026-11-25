import { KeyboardCode, type KeyboardCoordinateGetter } from "@dnd-kit/core";

import { BOARD_COLUMNS } from "./application-model";

export type BoardPoint = { x: number; y: number };
export type BoardSize = { width: number; height: number };
export type BoardRect = { left: number; top: number; width: number; height: number };

/** Pixels moved per Up or Down key press. Up and Down never leave the column. */
export const VERTICAL_STEP_PX = 40;

const HORIZONTAL_KEYS: readonly string[] = [KeyboardCode.Left, KeyboardCode.Right];
const VERTICAL_KEYS: readonly string[] = [KeyboardCode.Up, KeyboardCode.Down];

/**
 * Where the dragged card should move for one arrow key, or undefined to stay put.
 *
 * Left and Right move the card to the centre of the neighbouring column, keeping its height.
 * Up and Down move it within the column it is over, clamped so it stays inside that column.
 * The column is the one whose centre is nearest the card's centre, so repeated presses walk
 * one column at a time. `columnRect` returns a column's rectangle, or undefined when it is
 * not measured; `columns` is in board order.
 */
export function boardKeyboardMove(
  code: string,
  current: BoardPoint,
  dragged: BoardSize,
  columnRect: (column: string) => BoardRect | undefined,
  columns: readonly string[] = BOARD_COLUMNS
): BoardPoint | undefined {
  const centreX = current.x + dragged.width / 2;
  let index = -1;
  let nearest = Number.POSITIVE_INFINITY;
  columns.forEach((column, i) => {
    const rect = columnRect(column);
    if (!rect) return;
    const distance = Math.abs(rect.left + rect.width / 2 - centreX);
    if (distance < nearest) {
      nearest = distance;
      index = i;
    }
  });
  if (index < 0) return undefined;

  if (HORIZONTAL_KEYS.includes(code)) {
    const next = index + (code === KeyboardCode.Right ? 1 : -1);
    if (next < 0 || next >= columns.length) return undefined;
    const target = columnRect(columns[next]);
    if (!target) return undefined;
    return { x: target.left + target.width / 2 - dragged.width / 2, y: current.y };
  }

  if (VERTICAL_KEYS.includes(code)) {
    const rect = columnRect(columns[index]);
    if (!rect) return undefined;
    const step = code === KeyboardCode.Down ? VERTICAL_STEP_PX : -VERTICAL_STEP_PX;
    const top = rect.top;
    const bottom = Math.max(top, rect.top + rect.height - dragged.height);
    const y = Math.min(bottom, Math.max(top, current.y + step));
    return { x: current.x, y };
  }

  return undefined;
}

/**
 * dnd-kit keyboard coordinate getter for the stage board. Arrow keys are handled here and the
 * page does not scroll under them. Other keys go to the sensor's defaults.
 */
export const boardKeyboardCoordinates: KeyboardCoordinateGetter = (event, { currentCoordinates, context }) => {
  const isArrow = HORIZONTAL_KEYS.includes(event.code) || VERTICAL_KEYS.includes(event.code);
  if (!isArrow) return undefined;
  event.preventDefault();

  const collision = context.collisionRect;
  if (!collision) return undefined;
  return boardKeyboardMove(
    event.code,
    currentCoordinates,
    { width: collision.width, height: collision.height },
    (column) => context.droppableRects.get(column)
  );
};
