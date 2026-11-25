/**
 * Routes whose pages read the date range (`useDateRange`). The top bar shows the range picker only
 * on these. Any other route would show a control that changes nothing on that page.
 */
export const DATE_RANGE_ROUTES: readonly string[] = ["/", "/insights"];

export function routeUsesDateRange(pathname: string): boolean {
  return DATE_RANGE_ROUTES.includes(pathname);
}
