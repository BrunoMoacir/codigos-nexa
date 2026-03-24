import { clsx } from 'clsx';

interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  color?: 'purple' | 'green' | 'yellow' | 'red';
}

export const KpiCard: React.FC<KpiCardProps> = ({
  label,
  value,
  sub,
  color = 'purple'
}) => {
  return (
    <div className={clsx('kpi-card', `kpi-${color}`)}>
      <div className="kpi-content">
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{value}</div>
        {sub && <div className="kpi-sub">{sub}</div>}
      </div>
    </div>
  );
};
