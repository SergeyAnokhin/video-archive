export const visualModes = ["strict", "playful", "casino"];

const settingsSectionIds = ["source", "profiles", "preview", "playback", "tagging", "providers", "backup", "maintenance"];

export function getSettingsSections(t) {
  return settingsSectionIds.map((id) => ({ id, label: t(`settings.${id}`) }));
}

export function getNextVisualMode(current) {
  const index = visualModes.indexOf(current);
  return visualModes[(index + 1) % visualModes.length] ?? visualModes[0];
}
