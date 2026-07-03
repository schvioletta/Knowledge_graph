export default function Card({ as: Tag = "div", className = "", children, ...props }) {
  return (
    <Tag
      className={`rounded-md border border-ink/15 bg-surface ${className}`}
      {...props}
    >
      {children}
    </Tag>
  );
}
