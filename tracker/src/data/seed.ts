/**
 * Sample portfolio data. Clearly labeled: every row carries
 * isSample: true and the UI shows a Sample tag next to these names.
 * Real sites get added through the Sites screen; nothing here is
 * invented portfolio data, just a small fixture so screens render.
 */

import type { Page, Role, Site, User } from "./types";

export const SEED_SITES: Site[] = [
  {
    id: "site_sample_main",
    name: "Sample University Department",
    baseUrl: "https://dept.example.edu",
    isSample: true,
  },
  {
    id: "site_sample_lab",
    name: "Sample Research Lab",
    baseUrl: "https://lab.example.edu",
    isSample: true,
  },
];

export const SEED_PAGES: Page[] = [
  {
    id: "page_sample_home",
    siteId: "site_sample_main",
    url: "https://dept.example.edu/",
    title: "Department home",
    isSample: true,
  },
  {
    id: "page_sample_people",
    siteId: "site_sample_main",
    url: "https://dept.example.edu/people",
    title: "People directory",
    isSample: true,
  },
  {
    id: "page_sample_courses",
    siteId: "site_sample_main",
    url: "https://dept.example.edu/courses",
    title: "Course listings",
    isSample: true,
  },
  {
    id: "page_sample_contact",
    siteId: "site_sample_main",
    url: "https://dept.example.edu/contact",
    title: "Contact and help",
    isSample: true,
  },
  {
    id: "page_sample_lab_home",
    siteId: "site_sample_lab",
    url: "https://lab.example.edu/",
    title: "Lab home",
    isSample: true,
  },
  {
    id: "page_sample_lab_pubs",
    siteId: "site_sample_lab",
    url: "https://lab.example.edu/publications",
    title: "Publications",
    isSample: true,
  },
];

export const SEED_ROLES: Role[] = [
  { id: "role_lead", name: "lead" },
  { id: "role_tester", name: "tester" },
  { id: "role_developer", name: "developer" },
];

export const SEED_USERS: User[] = [
  { id: "user_sample_lead", name: "Sample Lead", roleId: "role_lead" },
  { id: "user_sample_tester", name: "Sample Tester", roleId: "role_tester" },
];
