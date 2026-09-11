import { Coffee, Cookie, CupSoda, IceCreamCone, Salad, Soup, UtensilsCrossed } from "lucide-react";
import { useState } from "react";

const ICONS: Record<string, typeof Salad> = {
  breakfast: Coffee,
  main: UtensilsCrossed,
  side: Salad,
  snack: Cookie,
  dessert: IceCreamCone,
  beverage: CupSoda,
};

interface Props {
  src: string | null;
  course: string | null;
  alt: string;
  className?: string;
  label?: boolean;
}

// A recipe photo, or a course-coloured placeholder when there is none or it fails to load.
export default function Photo({ src, course, alt, className = "", label = true }: Props) {
  const [failed, setFailed] = useState(false);
  if (src && !failed) {
    return <img className={`photo ${className}`} src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} />;
  }
  const Icon = ICONS[course ?? ""] ?? Soup;
  return (
    <div className={`photo photo-empty course-${course ?? "none"} ${className}`} role="img" aria-label={`${alt}, no photo`}>
      <Icon size={36} strokeWidth={1.4} />
      {label && <span>No photo</span>}
    </div>
  );
}
