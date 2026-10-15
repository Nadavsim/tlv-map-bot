import { Beef, Coffee, Fish, Flame, Hamburger, Pizza, Soup, Utensils, Wheat, Wine, type LucideIcon } from 'lucide-react'

// Categories are whatever the My Maps layers are called, so this can't be
// exhaustive: a layer added later (or "miscellaneous") gets the generic
// fork-and-knife until someone picks it an icon here. Keys are lowercase.
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  coffee: Coffee,
  burger: Hamburger,
  'wine bar': Wine,
  italian: Wheat,
  japanese: Fish,
  thai: Soup,
  steakhouse: Beef,
  mexican: Flame,
  pizza: Pizza,
}

export function CategoryIcon({ category, size = 12 }: { category: string; size?: number }) {
  const Icon = CATEGORY_ICONS[category.trim().toLowerCase()] ?? Utensils
  return <Icon size={size} aria-hidden="true" />
}
