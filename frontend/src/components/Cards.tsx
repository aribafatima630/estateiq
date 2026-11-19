import { Building2, Landmark, MapPin, BedDouble, Bath, Ruler, ExternalLink } from "lucide-react";
import type { Citation, ComparisonTable, ProjectCard, PropertyCard } from "../types";

function money(price: number | null, currency: string | null) {
  if (price == null) return "Price not published";
  const formatted = new Intl.NumberFormat("en-SA", { maximumFractionDigits: 0 }).format(price);
  return `${formatted} ${currency || ""}`.trim();
}

export function PropertyCards({ items }: { items: PropertyCard[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      {items.map((item) => (
        <a
          key={item.id}
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          className="group rounded-2xl border border-line bg-white p-4 shadow-card transition hover:-translate-y-0.5"
        >
          <div className="mb-2 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.16em] text-gold">
            <span>Wasalt listing</span>
            <ExternalLink size={14} />
          </div>
          <h3 className="font-serif text-xl leading-tight text-ink">{item.title}</h3>
          <p className="mt-2 text-sm text-mist">{item.location || item.city || "Location not published"}</p>
          <p className="mt-3 font-medium text-ink">{money(item.price, item.currency)}</p>
          <div className="mt-3 flex flex-wrap gap-3 text-xs text-navy">
            {item.property_type && (
              <span className="inline-flex items-center gap-1">
                <Building2 size={13} /> {item.property_type}
              </span>
            )}
            {item.bedrooms != null && (
              <span className="inline-flex items-center gap-1">
                <BedDouble size={13} /> {item.bedrooms} bed
              </span>
            )}
            {item.bathrooms != null && (
              <span className="inline-flex items-center gap-1">
                <Bath size={13} /> {item.bathrooms} bath
              </span>
            )}
            {item.area_sqm != null && (
              <span className="inline-flex items-center gap-1">
                <Ruler size={13} /> {item.area_sqm} SQM
              </span>
            )}
          </div>
        </a>
      ))}
    </div>
  );
}

export function ProjectCards({ items }: { items: ProjectCard[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-4 grid gap-3">
      {items.map((item) => (
        <a
          key={item.id}
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          className="rounded-2xl border border-line bg-white p-4 shadow-card transition hover:-translate-y-0.5"
        >
          <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-[0.16em] text-gold">
            <span className="inline-flex items-center gap-1">
              <Landmark size={13} /> DarGlobal development
            </span>
            <ExternalLink size={14} />
          </div>
          <h3 className="font-serif text-xl text-ink">{item.title}</h3>
          {item.location && (
            <p className="mt-1 inline-flex items-center gap-1 text-sm text-mist">
              <MapPin size={13} /> {item.location}
            </p>
          )}
          <p className="mt-3 text-sm leading-6 text-navy/80">{item.summary}</p>
          {item.brands.length > 0 && (
            <p className="mt-3 text-xs uppercase tracking-[0.14em] text-gold">{item.brands.join(" · ")}</p>
          )}
        </a>
      ))}
    </div>
  );
}

export function CitationList({ items }: { items: Citation[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {items.map((item) => (
        <a
          key={item.source_url}
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          className="max-w-full rounded-full border border-line bg-sand px-3 py-1.5 text-xs text-navy hover:border-gold"
        >
          <span className="uppercase tracking-[0.14em] text-gold">{item.source}</span>
          <span className="mx-2 text-line">/</span>
          <span className="truncate">{item.title}</span>
        </a>
      ))}
    </div>
  );
}

export function Comparison({ table }: { table: ComparisonTable | null }) {
  if (!table) return null;
  return (
    <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-white">
      <table className="w-full min-w-[520px] text-left text-sm">
        <thead className="bg-ink text-sand">
          <tr>
            <th className="px-4 py-3 font-medium">Indexed fact</th>
            {table.columns.map((column) => (
              <th key={column} className="px-4 py-3 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row) => (
            <tr key={row.label} className="border-t border-line align-top">
              <th className="px-4 py-3 font-medium text-ink">{row.label}</th>
              {row.values.map((value, index) => (
                <td key={`${row.label}-${index}`} className="px-4 py-3 text-navy/80">
                  {value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
