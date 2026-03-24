interface SectionHeaderProps {
  icon: string;
  title: string;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({ icon, title }) => {
  return (
    <div className="section-header">
      <span className="icon">{icon}</span>
      <span className="title">{title}</span>
    </div>
  );
};
