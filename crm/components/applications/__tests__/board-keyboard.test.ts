import { KeyboardCode } from "@dnd-kit/core";
import { describe, expect, it } from "vitest";

import { BOARD_COLUMNS } from "@/components/applications/application-model";
import { VERTICAL_STEP_PX, boardKeyboardMove, type BoardRect } from "@/components/applications/board-keyboard";

const COLUMN_WIDTH = 200;
const COLUMN_HEIGHT = 500;
const TOP = 40;
const CARD = { width: 180, height: 80 };

/** Six columns side by side, each COLUMN_WIDTH wide, starting at x = 0. */
function columnRect(column: string): BoardRect | undefined {
  const index = BOARD_COLUMNS.indexOf(column as (typeof BOARD_COLUMNS)[number]);
  if (index < 0) return undefined;
  return { left: index * COLUMN_WIDTH, top: TOP, width: COLUMN_WIDTH, height: COLUMN_HEIGHT };
}

/** A card whose left edge is `left`, sitting `top` pixels down. */
function at(left: number, top = TOP + 100) {
  return { x: left, y: top };
}

/** The card's centre x when its left edge is at `x`. */
const centreOf = (x: number) => x + CARD.width / 2;

function columnOf(x: number): string | undefined {
  const centre = centreOf(x);
  return BOARD_COLUMNS.find((column) => {
    const rect = columnRect(column)!;
    return centre >= rect.left && centre < rect.left + rect.width;
  });
}

describe("boardKeyboardMove, horizontal keys", () => {
  it("moves a card from Applied to the centre of Screening on Right", () => {
    const start = at(centreOf(0) - CARD.width / 2);
    const next = boardKeyboardMove(KeyboardCode.Right, start, CARD, columnRect);

    expect(next).toEqual({ x: COLUMN_WIDTH + COLUMN_WIDTH / 2 - CARD.width / 2, y: start.y });
    expect(columnOf(next!.x)).toBe("screening");
  });

  it("walks one column per press, not back to the same column", () => {
    let position = at(COLUMN_WIDTH / 2 - CARD.width / 2);
    const visited: string[] = [];
    for (let press = 0; press < 3; press += 1) {
      position = boardKeyboardMove(KeyboardCode.Right, position, CARD, columnRect)!;
      visited.push(columnOf(position.x)!);
    }

    expect(visited).toEqual(["screening", "tech_interview", "onsite"]);
  });

  it("moves back one column on Left", () => {
    const fromScreening = at(COLUMN_WIDTH * 1.5 - CARD.width / 2);
    const next = boardKeyboardMove(KeyboardCode.Left, fromScreening, CARD, columnRect);

    expect(columnOf(next!.x)).toBe("applied");
  });

  it("does nothing past the first or last column", () => {
    expect(boardKeyboardMove(KeyboardCode.Left, at(0), CARD, columnRect)).toBeUndefined();
    const lastColumn = at(COLUMN_WIDTH * 5.5 - CARD.width / 2);
    expect(boardKeyboardMove(KeyboardCode.Right, lastColumn, CARD, columnRect)).toBeUndefined();
  });

  it("does nothing when the neighbouring column has not been measured", () => {
    const unmeasured = (column: string) => (column === "screening" ? undefined : columnRect(column));
    const start = at(COLUMN_WIDTH / 2 - CARD.width / 2);

    expect(boardKeyboardMove(KeyboardCode.Right, start, CARD, unmeasured)).toBeUndefined();
  });

  it("does nothing when no column has been measured", () => {
    expect(boardKeyboardMove(KeyboardCode.Right, at(0), CARD, () => undefined)).toBeUndefined();
  });
});

describe("boardKeyboardMove, vertical keys", () => {
  it("keeps the card in its column on Up and Down", () => {
    const start = at(COLUMN_WIDTH * 2.5 - CARD.width / 2, TOP + 200);
    const down = boardKeyboardMove(KeyboardCode.Down, start, CARD, columnRect)!;
    const up = boardKeyboardMove(KeyboardCode.Up, down, CARD, columnRect)!;

    expect(down).toEqual({ x: start.x, y: start.y + VERTICAL_STEP_PX });
    expect(up).toEqual({ x: start.x, y: start.y });
    expect(columnOf(down.x)).toBe("tech_interview");
  });

  it("clamps Up and Down inside the column", () => {
    const top = boardKeyboardMove(KeyboardCode.Up, at(0, TOP + 5), CARD, columnRect)!;
    expect(top.y).toBe(TOP);

    const bottomLimit = TOP + COLUMN_HEIGHT - CARD.height;
    const bottom = boardKeyboardMove(KeyboardCode.Down, at(0, bottomLimit - 5), CARD, columnRect)!;
    expect(bottom.y).toBe(bottomLimit);
  });
});

describe("boardKeyboardMove, other keys", () => {
  it("ignores keys that are not arrows", () => {
    expect(boardKeyboardMove("KeyA", at(0), CARD, columnRect)).toBeUndefined();
  });
});
