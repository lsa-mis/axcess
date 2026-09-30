/**
 * The page's query string as it is now, for building the next one.
 *
 * A view kept in the URL is updated with React Router's functional form,
 * `setParams((previous) => …)`, but its `previous` is the query string of
 * the last render, not the live one. A search box publishes on a debounce,
 * so when the reader changed a filter while a keystroke was pending, the
 * search's update started from a query string without the filter and put it
 * back as it was: the filter was lost, for good (the Issues test for exactly
 * that failed about one run in three). The browser's own address is updated
 * as soon as the router navigates, so building from it keeps every change.
 */
export function liveSearchParams(): URLSearchParams {
  return new URLSearchParams(window.location.search);
}
