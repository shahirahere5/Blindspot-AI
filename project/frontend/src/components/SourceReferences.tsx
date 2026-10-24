import type { NormalizedDocument } from "../types/api";

interface SourceReferencesProps {
  locations: number[];
  document: NormalizedDocument;
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function SourceReferences({ locations, document }: SourceReferencesProps) {
  const uniqueLocations = [...new Set(locations)];
  if (uniqueLocations.length === 0) return null;

  return (
    <div className="source-list" aria-label="Document sources">
      {uniqueLocations.map((location) => {
        const block = document.content.find((item) => item.location === location);
        const label = block ? `${titleCase(block.type)} ${location}` : `Source ${location}`;
        return <span className="source-chip" key={location}>{label}</span>;
      })}
    </div>
  );
}
