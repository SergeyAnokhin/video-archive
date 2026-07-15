import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Tag } from '../types/api'
import { TagChipEditor } from './TagChipEditor'

// A separate, centrally-managed pool from the AI vocabulary above (user
// request): purely subjective tags a vision model could never determine,
// attached to a file through their own dedicated picker (`FileInfoPanel`,
// the playback screen) rather than the free-text add field, which creates
// ad-hoc tags in neither pool.
export function UserDefinedTagsSection() {
  const { t } = useTranslation()
  const [tags, setTags] = useState<Tag[]>([])

  const refresh = useCallback(async () => {
    const res = await fetch('/api/tags?category=user')
    if (res.ok) {
      const data: { tags: Tag[] } = await res.json()
      setTags(data.tags)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('tagging.userDefinedTitle')}</h3>

      <TagChipEditor
        tags={tags}
        onChanged={refresh}
        createDefaults={{ is_ai_vocabulary: false, is_user_defined: true }}
        hintText={t('tagging.userDefinedHint')}
        emptyText={t('tagging.userDefinedEmpty')}
        placeholderText={t('tagging.userDefinedNewTagPlaceholder')}
      />
    </section>
  )
}
