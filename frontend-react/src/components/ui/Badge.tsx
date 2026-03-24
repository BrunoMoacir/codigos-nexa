import { clsx } from 'clsx';

interface BadgeProps {
  children: string;
  color?: 'green' | 'yellow' | 'red' | 'purple';
}

export const Badge: React.FC<BadgeProps> = ({ children, color = 'purple' }) => {
  return (
    <span className={clsx('badge', `badge-${color}`)}>
      {children}
    </span>
  );
};
