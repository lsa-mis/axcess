/**
 * Regression test for the Test Runner setup form.
 *
 * The bug this pins: the site dropdown's change handler used to issue
 * two separate search-param updates built from the same stale params
 * snapshot, so the second update erased the first and selecting a site
 * looked dead. The fix is one atomic update (and a functional updater
 * for single-key changes). These tests drive the real component
 * through MemoryRouter and fail if the stomp ever returns.
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { store } from "../data/store";
import TestRunnerRoute from "./TestRunner";

function renderRunner() {
  return render(
    <MemoryRouter initialEntries={["/runner"]}>
      <TestRunnerRoute />
    </MemoryRouter>,
  );
}

describe("Test Runner setup", () => {
  beforeEach(() => {
    store.reset();
  });
  afterEach(cleanup);

  it("keeps the site selected after choosing it", async () => {
    const user = userEvent.setup();
    renderRunner();

    const siteSelect = screen.getByLabelText<HTMLSelectElement>("Site");
    await user.selectOptions(siteSelect, "site_sample_main");

    expect(siteSelect.value).toBe("site_sample_main");
    // The page dropdown unlocks once a site is chosen.
    const pageSelect = screen.getByLabelText<HTMLSelectElement>("Page");
    expect(pageSelect.disabled).toBe(false);
  });

  it("choosing a new site clears the previously chosen page", async () => {
    const user = userEvent.setup();
    renderRunner();

    const siteSelect = screen.getByLabelText<HTMLSelectElement>("Site");
    const pageSelect = screen.getByLabelText<HTMLSelectElement>("Page");

    await user.selectOptions(siteSelect, "site_sample_main");
    await user.selectOptions(pageSelect, "page_sample_home");
    expect(pageSelect.value).toBe("page_sample_home");

    await user.selectOptions(siteSelect, "site_sample_lab");
    expect(siteSelect.value).toBe("site_sample_lab");
    expect(pageSelect.value).toBe("");
  });

  it("enables Start only when site, page, and an enabled module are set", async () => {
    const user = userEvent.setup();
    renderRunner();

    const start = screen.getByRole<HTMLButtonElement>("button", {
      name: /Start run/,
    });
    expect(start.disabled).toBe(true);

    await user.selectOptions(
      screen.getByLabelText<HTMLSelectElement>("Site"),
      "site_sample_main",
    );
    await user.selectOptions(
      screen.getByLabelText<HTMLSelectElement>("Page"),
      "page_sample_home",
    );
    await user.click(
      screen.getByRole("radio", { name: /Module A/ }),
    );

    expect(start.disabled).toBe(false);
  });

  it("starting a run shows the first Module A check", async () => {
    const user = userEvent.setup();
    renderRunner();

    await user.selectOptions(
      screen.getByLabelText<HTMLSelectElement>("Site"),
      "site_sample_main",
    );
    await user.selectOptions(
      screen.getByLabelText<HTMLSelectElement>("Page"),
      "page_sample_home",
    );
    await user.click(screen.getByRole("radio", { name: /Module A/ }));
    await user.click(screen.getByRole("button", { name: /Start run/ }));

    expect(
      screen.getByRole("heading", {
        name: "Tab order matches reading order",
      }),
    ).toBeTruthy();
    expect(screen.getByText("Check 1 of 8")).toBeTruthy();
  });
});
