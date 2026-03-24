import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from '../../../components/ui/Badge';

describe('Badge', () => {
  it('renders text content', () => {
    render(<Badge>Active</Badge>);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('applies color class', () => {
    const { container } = render(<Badge color="green">Success</Badge>);
    const badge = container.querySelector('.badge-green');
    expect(badge).toBeInTheDocument();
  });
});
