export const visualModes = ["strict", "playful", "casino"];

const settingsSections = [
  { id: "source", icon: "database" },
  { id: "profiles", icon: "sliders" },
  { id: "preview", icon: "image" },
  { id: "playback", icon: "clapperboard" },
  { id: "tagging", icon: "tags" },
  { id: "providers", icon: "bot" },
  { id: "backup", icon: "archive" },
  { id: "maintenance", icon: "wrench" }
];

export function getSettingsSections(t) {
  return settingsSections.map((section) => ({ ...section, label: t(`settings.${section.id}`) }));
}

export function getNextVisualMode(current) {
  const index = visualModes.indexOf(current);
  return visualModes[(index + 1) % visualModes.length] ?? visualModes[0];
}
