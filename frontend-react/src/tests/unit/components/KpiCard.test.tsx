import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KpiCard } from '../../../components/ui/KpiCard';

describe('KpiCard', () => {
  it('renders label and value', () => {
    render(<KpiCard label="Renda" value="R$ 10.000" />);

    expect(screen.getByText('Renda')).toBeInTheDocument();
    expect(screen.getByText('R$ 10.000')).toBeInTheDocument();
  });

  it('renders optional sub text', () => {
    render(<KpiCard label="Score" value="85" sub="+5 pontos" />);

    expect(screen.getByText('+5 pontos')).toBeInTheDocument();
  });

  it('applies correct color class', () => {
    const { container } = render(
      <KpiCard label="Safe to Spend" value="R$ 2.500" color="green" />
    );

    const card = container.querySelector('.kpi-green');
    expect(card).toBeInTheDocument();
  });

  it('defaults to purple color', () => {
    const { container } = render(<KpiCard label="Total" value="R$ 1.000" />);

    const card = container.querySelector('.kpi-purple');
    expect(card).toBeInTheDocument();
  });
});
