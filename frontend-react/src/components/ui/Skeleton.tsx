interface SkeletonProps {
  lines?: number;
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({ lines = 4, className }) => {
  return (
    <div className={className}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="skeleton h-4 mb-3"
          style={{ width: `${95 - (i % 3) * 15}%` }}
        />
      ))}
    </div>
  );
};
