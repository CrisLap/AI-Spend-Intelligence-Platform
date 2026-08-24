export default function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-border bg-panel backdrop-blur-md shadow-glass ${className}`}>
      {children}
    </div>
  );
}
