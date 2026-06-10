/**
 * Sites and pages inventory. Add real sites and pages here; the seed
 * rows are labeled Sample so nobody mistakes fixture data for the
 * portfolio.
 */

import { useState } from "react";
import { newId, store } from "../data/store";
import { useAppData } from "../data/useStore";
import {
  Button,
  Card,
  Field,
  PageTitle,
  SampleTag,
  inputClass,
} from "../components/ui";

export default function SitesRoute() {
  const data = useAppData();
  const [siteName, setSiteName] = useState("");
  const [siteUrl, setSiteUrl] = useState("");
  const [pageSite, setPageSite] = useState("");
  const [pageTitle, setPageTitle] = useState("");
  const [pageUrl, setPageUrl] = useState("");
  const [feedback, setFeedback] = useState("");

  const addSite = () => {
    if (!siteName.trim() || !siteUrl.trim()) {
      setFeedback("A site needs a name and a base URL.");
      return;
    }
    store.mutate((d) => {
      d.sites.push({
        id: newId("site"),
        name: siteName.trim(),
        baseUrl: siteUrl.trim(),
        isSample: false,
      });
    });
    setSiteName("");
    setSiteUrl("");
    setFeedback("Site added.");
  };

  const addPage = () => {
    if (!pageSite || !pageTitle.trim() || !pageUrl.trim()) {
      setFeedback("A page needs a site, a title, and a URL.");
      return;
    }
    store.mutate((d) => {
      d.pages.push({
        id: newId("page"),
        siteId: pageSite,
        title: pageTitle.trim(),
        url: pageUrl.trim(),
        isSample: false,
      });
    });
    setPageTitle("");
    setPageUrl("");
    setFeedback("Page added.");
  };

  return (
    <>
      <PageTitle
        title="Sites"
        subtitle="The portfolio under test. Pages belong to sites; test runs and issues belong to pages."
      />

      <p role="status" aria-live="polite" className="mb-3 font-semibold">
        {feedback}
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 text-lg font-bold">Add a site</h2>
          <div className="flex flex-col gap-3">
            <Field label="Site name" htmlFor="site-name">
              <input
                id="site-name"
                className={inputClass}
                value={siteName}
                onChange={(e) => setSiteName(e.target.value)}
              />
            </Field>
            <Field label="Base URL" htmlFor="site-url">
              <input
                id="site-url"
                type="url"
                className={inputClass}
                value={siteUrl}
                placeholder="https://example.edu"
                onChange={(e) => setSiteUrl(e.target.value)}
              />
            </Field>
            <div>
              <Button variant="primary" onClick={addSite}>
                Add site
              </Button>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="mb-3 text-lg font-bold">Add a page</h2>
          <div className="flex flex-col gap-3">
            <Field label="Site" htmlFor="page-site">
              <select
                id="page-site"
                className={inputClass}
                value={pageSite}
                onChange={(e) => setPageSite(e.target.value)}
              >
                <option value="">Choose a site</option>
                {data.sites.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Page title" htmlFor="page-title">
              <input
                id="page-title"
                className={inputClass}
                value={pageTitle}
                onChange={(e) => setPageTitle(e.target.value)}
              />
            </Field>
            <Field label="Page URL" htmlFor="page-url">
              <input
                id="page-url"
                type="url"
                className={inputClass}
                value={pageUrl}
                onChange={(e) => setPageUrl(e.target.value)}
              />
            </Field>
            <div>
              <Button variant="primary" onClick={addPage}>
                Add page
              </Button>
            </div>
          </div>
        </Card>
      </div>

      <h2 className="mb-2 mt-6 text-lg font-bold">Portfolio</h2>
      <div className="flex flex-col gap-4">
        {data.sites.map((site) => {
          const pages = data.pages.filter((p) => p.siteId === site.id);
          return (
            <Card key={site.id} className="p-4">
              <h3 className="flex flex-wrap items-center gap-2 text-base font-bold">
                {site.name} {site.isSample ? <SampleTag /> : null}
                <span className="text-sm font-normal text-ink-muted">
                  {site.baseUrl}
                </span>
              </h3>
              <ul className="mt-2 divide-y divide-line">
                {pages.map((p) => (
                  <li key={p.id} className="flex flex-wrap gap-2 py-2">
                    <span className="font-semibold">{p.title}</span>
                    <span className="break-all text-sm text-ink-muted">
                      {p.url}
                    </span>
                  </li>
                ))}
                {pages.length === 0 ? (
                  <li className="py-2 text-ink-muted">No pages yet.</li>
                ) : null}
              </ul>
            </Card>
          );
        })}
      </div>
    </>
  );
}
