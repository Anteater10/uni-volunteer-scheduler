import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Render an assistant message as Markdown.
 *
 * The model has always written Markdown — headings, `**bold**`, `-` lists,
 * tables. The drawer rendered it inside `whitespace-pre-wrap`, so a reply
 * listing twelve capabilities arrived as a wall of asterisks and hyphens,
 * and the one structure that mattered (which of those are read-only and
 * which need your approval) was the hardest part to see.
 *
 * There is no `@tailwindcss/typography` in this project, so every element
 * is styled explicitly below rather than by a `prose` class. That is more
 * lines, but it keeps the bubble's type scale under our control instead of
 * a plugin's defaults.
 *
 * Raw HTML is not enabled. react-markdown ignores it unless `rehype-raw` is
 * added, which is the behaviour we want for text a language model produced.
 */
export default function MarkdownMessage({ children }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Paragraphs carry the spacing; `space-y` on the wrapper can't,
        // because Markdown emits loose and tight lists differently.
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        strong: ({ children }) => (
          <strong className="font-semibold text-gray-900">{children}</strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
        // Section headings inside a chat bubble should read as labels, not
        // as page titles — the bubble is already the visual container.
        h1: ({ children }) => (
          <h4 className="mt-3 mb-1.5 first:mt-0 font-semibold text-gray-900">
            {children}
          </h4>
        ),
        h2: ({ children }) => (
          <h4 className="mt-3 mb-1.5 first:mt-0 font-semibold text-gray-900">
            {children}
          </h4>
        ),
        h3: ({ children }) => (
          <h4 className="mt-3 mb-1.5 first:mt-0 font-semibold text-gray-900">
            {children}
          </h4>
        ),
        h4: ({ children }) => (
          <h4 className="mt-3 mb-1.5 first:mt-0 font-semibold text-gray-900">
            {children}
          </h4>
        ),
        ul: ({ children }) => (
          <ul className="mb-2 last:mb-0 space-y-1 list-disc pl-5 marker:text-gray-400">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 last:mb-0 space-y-1 list-decimal pl-5 marker:text-gray-400">
            {children}
          </ol>
        ),
        li: ({ children }) => <li className="pl-0.5">{children}</li>,
        code: ({ inline, children }) =>
          inline ? (
            <code className="rounded bg-gray-200/70 px-1 py-0.5 font-mono text-[0.85em]">
              {children}
            </code>
          ) : (
            <code className="font-mono text-[0.85em]">{children}</code>
          ),
        pre: ({ children }) => (
          // Code and tables get their own scroller so a long line scrolls
          // the block, never the drawer.
          <pre className="mb-2 last:mb-0 overflow-x-auto rounded bg-gray-200/70 p-2 text-[0.85em]">
            {children}
          </pre>
        ),
        table: ({ children }) => (
          <div className="mb-2 last:mb-0 overflow-x-auto">
            <table className="w-full border-collapse text-left">
              {children}
            </table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border-b border-gray-300 pb-1 pr-3 font-semibold">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="border-b border-gray-200 py-1 pr-3 align-top">
            {children}
          </td>
        ),
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-indigo-700"
          >
            {children}
          </a>
        ),
        hr: () => <hr className="my-3 border-gray-300" />,
        blockquote: ({ children }) => (
          <blockquote className="mb-2 last:mb-0 border-l-2 border-gray-300 pl-3 text-gray-700">
            {children}
          </blockquote>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
