const PADDING = { none: "", md: "p-4", lg: "p-6", xl: "p-12" } as const;

export default function Card({
  children,
  className = "",
  padding = "md",
}: {
  children: React.ReactNode;
  className?: string;
  padding?: keyof typeof PADDING;
}) {
  return (
    <div className={`rounded-2xl border border-border bg-panel backdrop-blur-md shadow-glass ${PADDING[padding]} ${className}`}>
      {children}
    </div>
  );
}
