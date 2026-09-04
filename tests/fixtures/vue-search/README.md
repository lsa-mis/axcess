# Vue search regression app

Real Vue 3.5.13 and Vue Router 4.5.0, vendored from their npm packages so
tests require no network or package installation. Upstream licenses are in
`vendor/`. Vue's [browser build](https://vuejs.org/guide/quick-start.html#using-vue-from-cdn)
and Vue Router's [global build](https://router.vuejs.org/installation.html) are used.

The app has 51 reachable URLs: a search page, 24 report routes, 24 nested
detail routes, and two links created only after opening a menu. Search
results use clickable options without hrefs and arrive asynchronously in
three pages. `?router=hash` selects hash routing. `?auth=session` requires
the simulated sign-in button, with tab-scoped sessionStorage.

This is synthetic test data. It never authenticates against a real IdP or
requests a password or second factor. The integration test serves it only
on loopback and returns the SPA shell for history routes.
