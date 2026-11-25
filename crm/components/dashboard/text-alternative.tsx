import type { ReactNode } from "react";

export type AlternativeColumn<T> = {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
};

/**
 * Visually hidden table with the same numbers as a chart. Screen reader users and anyone
 * who needs exact values get it; sighted users see the chart. Keep it beside the chart,
 * not inside it, so the chart's image role does not hide the table.
 */
export function TextAlternative<T>({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: ReadonlyArray<AlternativeColumn<T>>;
  rows: readonly T[];
}) {
  // The wrapper carries sr-only, not the table: a table ignores a 1px width and would still
  // push the page sideways.
  return (
    <div className="sr-only">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column.key}>{column.cell(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
