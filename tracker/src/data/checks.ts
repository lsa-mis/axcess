/**
 * The check catalog, seeded from the six testing modules.
 *
 * Tier ownership comes from the "Accessibility Policy & Manual Testing
 * Mapping" workbook: its Policy Leverage Analysis sheet says how each
 * criterion is detected today (policy assisted, manual) and its
 * Leveraging AI sheet says which model class can take the work
 * (Text-LLM, VLM, Playwright runtime, embeddings). The routing rule:
 * give every check to the cheapest tier that can clear it, and leave
 * only confirm steps for humans.
 *
 * Tier meanings:
 *   automated   (T1)  deterministic rule checkers, axe style
 *   ai_assisted (T2)  policy or embedding pre-flag plus a human confirm
 *   agentic     (T3)  Playwright runtime probes (tab walks, form submits)
 *   manual      (T4)  human judgment end to end, guided by the runner
 *   local_vlm   (T5)  local vision or text model judgment on extracts
 */

import type { Check } from "./types";

export const CHECK_CATALOG: Check[] = [
  // Module A: Keyboard and focus
  {
    id: "A1",
    title: "Tab order matches reading order",
    wcag: "2.4.3",
    module: "A",
    tier: "agentic",
    expectedBehavior:
      "Press Tab from the top of the page. Focus should move in the same order a sighted reader would scan the page: left to right, top to bottom. Watch for jumps back up the page or into unrelated regions.",
  },
  {
    id: "A2",
    title: "All interactive elements are reachable by keyboard",
    wcag: "2.1.1",
    module: "A",
    tier: "agentic",
    expectedBehavior:
      "Tab through the whole page. Every link, button, form control, and custom widget must receive focus at some point. Anything mouse-only is a failure.",
  },
  {
    id: "A3",
    title: "No keyboard traps",
    wcag: "2.1.2",
    module: "A",
    tier: "agentic",
    expectedBehavior:
      "Use Tab and Shift+Tab to move in and out of every component, including embedded players and modals. If focus gets stuck anywhere and Escape does not free it, that is a trap.",
  },
  {
    id: "A4",
    title: "Visible focus indicator on every interactive element",
    wcag: "2.4.7",
    module: "A",
    tier: "local_vlm",
    expectedBehavior:
      "Tab through the page and confirm you can always see which element has focus. A focus ring must be clearly visible against the background, not removed by CSS.",
  },
  {
    id: "A5",
    title: "Focused element is not obscured",
    wcag: "2.4.11",
    module: "A",
    tier: "local_vlm",
    expectedBehavior:
      "Tab through the page with sticky headers, footers, and cookie banners open. The focused element must stay at least partially visible, never fully hidden behind overlays.",
  },
  {
    id: "A6",
    title: "Skip link is present and works",
    wcag: "2.4.1",
    module: "A",
    tier: "agentic",
    expectedBehavior:
      "Press Tab once on a fresh page load. A skip link should appear; activating it must move focus into the main content area, past the navigation.",
  },
  {
    id: "A7",
    title: "Custom widgets follow ARIA authoring practices",
    wcag: "4.1.2",
    module: "A",
    tier: "manual",
    expectedBehavior:
      "For each custom widget (menus, tabs, accordions, comboboxes), compare keyboard behavior with the ARIA Authoring Practices pattern: arrow keys, Home and End, Escape, Enter, and Space should all do what the pattern says.",
  },
  {
    id: "A8",
    title: "Focus moves logically when content changes",
    wcag: "2.4.3",
    module: "A",
    tier: "manual",
    expectedBehavior:
      "Trigger content changes: open a modal, submit a form, delete a list item. Focus should move somewhere sensible (into the modal, to the confirmation, to the next item), never silently reset to the top of the page.",
  },

  // Module B: Screen reader
  {
    id: "B1",
    title: "Reading order is meaningful",
    wcag: "1.3.2",
    module: "B",
    tier: "local_vlm",
    expectedBehavior:
      "Read the page top to bottom with a screen reader or in reader mode. The spoken order must match the visual story of the page, with no content arriving out of sequence.",
  },
  {
    id: "B2",
    title: "Headings convey the page structure",
    wcag: "1.3.1, 2.4.6",
    module: "B",
    tier: "local_vlm",
    expectedBehavior:
      "Pull up the heading list (VoiceOver rotor or NVDA H key). It should read like a sensible table of contents: one h1, levels that step down one at a time, and headings that describe their sections.",
  },
  {
    id: "B3",
    title: "Landmarks are present and correct",
    wcag: "1.3.1",
    module: "B",
    tier: "automated",
    expectedBehavior:
      "Check that the page has exactly one main landmark, plus nav, header, and footer landmarks where those regions exist. All perceivable content should live inside a landmark.",
  },
  {
    id: "B4",
    title: "Custom components expose name, role, and value",
    wcag: "4.1.2",
    module: "B",
    tier: "automated",
    expectedBehavior:
      "Focus each custom component with a screen reader running. It must announce a meaningful name, the right role (button, tab, checkbox), and its current state or value.",
  },
  {
    id: "B5",
    title: "Live regions announce status changes",
    wcag: "4.1.3",
    module: "B",
    tier: "agentic",
    expectedBehavior:
      "Trigger async updates: save a form, load search results, dismiss a toast. The screen reader should announce the outcome without focus moving there manually.",
  },
  {
    id: "B6",
    title: "Alt text quality",
    wcag: "1.1.1",
    module: "B",
    tier: "local_vlm",
    expectedBehavior:
      "For each informative image, the alt text must convey the same information as the image. Decorative images must have empty alt. Watch for filenames, placeholder text, and alt that repeats nearby visible text.",
  },
  {
    id: "B7",
    title: "Form labels and error association",
    wcag: "3.3.1, 3.3.2, 4.1.2",
    module: "B",
    tier: "local_vlm",
    expectedBehavior:
      "Focus every form field: each must announce a clear label. Submit with errors: each message must be announced and programmatically tied to its field, not just shown in red nearby.",
  },
  {
    id: "B8",
    title: "Link and button purpose is clear out of context",
    wcag: "2.4.4",
    module: "B",
    tier: "local_vlm",
    expectedBehavior:
      "Pull up the links list in the screen reader. Each entry should make sense on its own. Repeated entries like Read more or Click here are failures unless context is programmatically attached.",
  },

  // Module C: Visual and low vision
  {
    id: "C1",
    title: "Text contrast meets the minimum ratio",
    wcag: "1.4.3",
    module: "C",
    tier: "automated",
    expectedBehavior:
      "Body text needs 4.5 to 1 contrast against its background; large text needs 3 to 1. Automated tooling computes the pairs; confirm flagged cases on screen.",
  },
  {
    id: "C2",
    title: "Non-text contrast, including text over images",
    wcag: "1.4.11",
    module: "C",
    tier: "local_vlm",
    expectedBehavior:
      "Buttons, icons, form control borders, and focus indicators need 3 to 1 contrast against adjacent colors. Check text placed over photos or gradients in every state.",
  },
  {
    id: "C3",
    title: "Reflow at 320 px and 400 percent zoom",
    wcag: "1.4.10",
    module: "C",
    tier: "agentic",
    expectedBehavior:
      "Zoom the page to 400 percent or set the viewport to 320 px wide. Content must reflow into one column with no horizontal scrolling and no loss of content or function.",
  },
  {
    id: "C4",
    title: "Text spacing override does not break content",
    wcag: "1.4.12",
    module: "C",
    tier: "agentic",
    expectedBehavior:
      "Apply the WCAG text spacing overrides (line height 1.5, paragraph spacing 2x, letter spacing 0.12em, word spacing 0.16em). Nothing may clip, overlap, or disappear.",
  },
  {
    id: "C5",
    title: "Content on hover or focus is dismissible and persistent",
    wcag: "1.4.13",
    module: "C",
    tier: "agentic",
    expectedBehavior:
      "Hover and focus elements that reveal tooltips or menus. The revealed content must stay visible while the pointer moves to it, and Escape must dismiss it without moving focus.",
  },
  {
    id: "C6",
    title: "Color is not the only signal",
    wcag: "1.4.1",
    module: "C",
    tier: "local_vlm",
    expectedBehavior:
      "View the page in grayscale. Links, errors, required fields, chart series, and status indicators must still be identifiable through text, icons, underlines, or patterns.",
  },
  {
    id: "C7",
    title: "Text resizes to 200 percent without loss",
    wcag: "1.4.4",
    module: "C",
    tier: "agentic",
    expectedBehavior:
      "Use browser text-only zoom at 200 percent. All text must remain readable and functional with no clipping or overlap.",
  },
  {
    id: "C8",
    title: "Orientation is not locked",
    wcag: "1.3.4",
    module: "C",
    tier: "agentic",
    expectedBehavior:
      "View the page in portrait and landscape. Content and function must be available in both orientations unless one is essential.",
  },

  // Module D: Cognitive and content
  {
    id: "D1",
    title: "Page title describes the page",
    wcag: "2.4.2",
    module: "D",
    tier: "ai_assisted",
    expectedBehavior:
      "The browser tab title must identify the specific page and the site, in that order. Confirm flagged titles actually describe what the page is for.",
  },
  {
    id: "D2",
    title: "Navigation and components are consistent across pages",
    wcag: "3.2.3, 3.2.4",
    module: "D",
    tier: "ai_assisted",
    expectedBehavior:
      "Compare several pages. The navigation must appear in the same place and order, and repeated components must use consistent names (Search on one page should not become Find on another).",
  },
  {
    id: "D3",
    title: "Language of page and parts is declared",
    wcag: "3.1.1, 3.1.2",
    module: "D",
    tier: "automated",
    expectedBehavior:
      "The html element needs a correct lang attribute, and passages in another language need their own lang attribute so screen readers switch voices.",
  },
  {
    id: "D4",
    title: "Headings and labels are descriptive",
    wcag: "2.4.6",
    module: "D",
    tier: "local_vlm",
    expectedBehavior:
      "Each heading should describe its section and each form label should describe its field. Generic text like Details or More is a failure when the section is about something specific.",
  },
  {
    id: "D5",
    title: "Errors are identified, explained, and prevented",
    wcag: "3.3.1, 3.3.3, 3.3.4",
    module: "D",
    tier: "agentic",
    expectedBehavior:
      "Submit forms with bad input. Errors must name the field, say what went wrong, and suggest how to fix it. For legal or financial submissions, a review or confirm step must exist.",
  },
  {
    id: "D6",
    title: "Instructions do not rely on sensory characteristics",
    wcag: "1.3.3",
    module: "D",
    tier: "ai_assisted",
    expectedBehavior:
      "Find instructions that reference color, shape, or position (press the green button, see the box on the right). Each needs a non-sensory anchor such as the button name.",
  },

  // Module E: Media and motion
  {
    id: "E1",
    title: "Media has captions, audio description, and transcripts",
    wcag: "1.2.1, 1.2.2, 1.2.3, 1.2.4, 1.2.5",
    module: "E",
    tier: "ai_assisted",
    expectedBehavior:
      "For each audio or video: prerecorded audio needs a transcript, video needs captions, and video with important visuals needs audio description. Play a sample to verify quality, not just presence.",
  },
  {
    id: "E2",
    title: "Moving content can be paused, stopped, or hidden",
    wcag: "2.2.2",
    module: "E",
    tier: "local_vlm",
    expectedBehavior:
      "Find carousels, tickers, and auto-playing animation that lasts more than five seconds. Each must have a visible control to pause, stop, or hide it.",
  },
  {
    id: "E3",
    title: "Nothing flashes more than three times per second",
    wcag: "2.3.1",
    module: "E",
    tier: "automated",
    expectedBehavior:
      "Watch animations and video for rapid flashing. Frame analysis pre-flags candidates; confirm anything flagged stays under three flashes per second or is small enough to be exempt.",
  },
  {
    id: "E4",
    title: "Reduced motion preference is respected",
    wcag: "2.3.3",
    module: "E",
    tier: "agentic",
    expectedBehavior:
      "Enable the reduce motion setting in the OS. Non-essential animation (parallax, auto-playing transitions) should stop or simplify.",
  },

  // Module F: WCAG 2.2
  {
    id: "F1",
    title: "Focused element is not obscured (minimum)",
    wcag: "2.4.11",
    module: "F",
    tier: "local_vlm",
    expectedBehavior:
      "Tab through pages that have sticky bars or banners. The element with focus must never be entirely hidden by fixed content.",
  },
  {
    id: "F2",
    title: "Dragging has a single-pointer alternative",
    wcag: "2.5.7",
    module: "F",
    tier: "manual",
    expectedBehavior:
      "Find drag interactions (sliders, reordering, kanban). Each must offer a click or tap alternative such as buttons or a menu that performs the same action.",
  },
  {
    id: "F3",
    title: "Targets are at least 24 by 24 pixels",
    wcag: "2.5.8",
    module: "F",
    tier: "automated",
    expectedBehavior:
      "Interactive targets need at least 24 by 24 CSS pixels of hit area, or equivalent spacing from neighbors. Automated tooling flags small targets; confirm flagged ones.",
  },
  {
    id: "F4",
    title: "Help is in a consistent place",
    wcag: "3.2.6",
    module: "F",
    tier: "ai_assisted",
    expectedBehavior:
      "If pages offer help (contact link, chat, FAQ), it must appear in the same relative place on every page that has it.",
  },
  {
    id: "F5",
    title: "No redundant entry in multi-step flows",
    wcag: "3.3.7",
    module: "F",
    tier: "agentic",
    expectedBehavior:
      "Walk multi-step forms. Information entered in an earlier step must be auto-filled or selectable later, not demanded again from scratch.",
  },
  {
    id: "F6",
    title: "Authentication has no cognitive test",
    wcag: "3.3.8",
    module: "F",
    tier: "manual",
    expectedBehavior:
      "Test the login flow. Password managers and paste must work, and there must be no puzzle or memorization step without an alternative.",
  },
];

/** Checks for one module, in catalog order. */
export function checksForModule(module: string): Check[] {
  return CHECK_CATALOG.filter((c) => c.module === module);
}
