import { Fragment } from "react";

/** Offer a line break after each dot and slash, so a long host wraps
 *  between its labels instead of mid-word. */
export default function BreakableUrl({ text }: { text: string }) {
  const parts = text.split(/(?<=[./])/);
  return (
    <>
      {parts.map((part, index) => (
        <Fragment key={index}>
          {part}
          {index < parts.length - 1 && <wbr />}
        </Fragment>
      ))}
    </>
  );
}
