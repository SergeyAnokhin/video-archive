const messages = {
  en: {
    app: {
      title: "Library",
      brand: "Video Archive",
      summary:
        "Browse one active source, keep the main library light, and move playback, tuning, logs, and deeper file actions into dedicated modal flows.",
      noActiveSource: "No active source",
      queueSummary: "{{running}} running - {{queued}} queued",
      queueRuntime: "Runtime {{status}}",
      backendReady: "Backend {{status}}",
      backendLoading: "Connecting backend",
      backendOffline: "Backend offline",
      lastBackendError: "Last backend error: {{message}}",
      activeSource: "Active source",
      libraryRoot: "Library root",
      sourceRoot: "Source root"
    },
    common: {
      close: "Close",
      cancel: "Cancel",
      save: "Save",
      refresh: "Refresh",
      open: "Open",
      loading: "Loading...",
      default: "Default",
      none: "-",
      allLevels: "All levels"
    },
    header: {
      source: "Source",
      queue: "Queue",
      togglePreviewShow: "Show preview",
      togglePreviewHide: "Hide preview",
      scanSource: "Scan source",
      logs: "Logs",
      jobs: "Jobs",
      settings: "Settings",
      locale: "Language",
      theme: "Visual mode"
    },
    theme: {
      strict: "Strict",
      playful: "Playful",
      casino: "Casino"
    },
    directory: {
      kicker: "Directories",
      title: "Tree",
      rescanSource: "Rescan source",
      emptyTitle: "No scanned tree yet",
      emptyBody: "Save an active source, then run a source scan to populate the directory tree.",
      convertBadge: "convert",
      previewBadge: "preview"
    },
    files: {
      kicker: "Current folder",
      intro: "Primary toolbar stays focused on subtree work and lightweight file entry points.",
      details: "Details",
      playback: "Playback",
      backToParent: "Up one level",
      folderCard: "Folder",
      convertSubtree: "Convert subtree",
      previewSubtree: "Preview subtree",
      tagSubtree: "Tag subtree",
      rescanSubtree: "Rescan subtree",
      emptyTitle: "This folder is empty",
      emptyBody: "No folders or files are visible here yet, or the scan has not discovered them yet.",
      name: "Name",
      type: "Type",
      size: "Size",
      modified: "Modified",
      status: "Status",
      convertState: "Convert {{state}}",
      previewState: "Preview {{state}}"
    },
    previewPanel: {
      kicker: "Preview",
      directoryTitle: "Directory collage",
      fileTitle: "Selected asset",
      settings: "Preview settings",
      empty: "No preview asset yet. Run a file or subtree preview job.",
      summary:
        "{{sampleCount}} sampled frames with {{largeTileCount}} large tiles in {{timelineFlow}} flow.",
      fallbackSummary: "Preview generation is on-demand and remains separate from conversion and tagging.",
      selectedFolder: "Selected folder",
      visibleFiles: "Visible files",
      selectedFile: "Selected file",
      assignedTags: "Assigned tags",
      sampleCount: "Sample count",
      playbackMode: "Playback mode",
      aspectRatio: "Aspect ratio",
      closedVocabulary: "Closed-vocabulary tags",
      noTags: "No tags stored for the selected video yet. Run a file or subtree tagging job."
    },
    settings: {
      title: "Settings",
      source: "Source",
      profiles: "Profiles",
      preview: "Preview",
      playback: "Playback",
      tagging: "Tagging",
      providers: "Providers",
      backup: "Backup",
      maintenance: "Maintenance",
      secondaryFlow: "This section remains a secondary maintenance flow and stays out of the main library view."
    },
    sourceSettings: {
      intro:
        "Video Archive supports one active source at a time. Use a remote protocol for server-backed libraries or switch to a local folder when you want to test directly on this machine.",
      name: "Name",
      protocol: "Protocol",
      rootPath: "Root path",
      host: "Host",
      port: "Port",
      username: "Username",
      password: "Password",
      localOption: "Local folder",
      browse: "Browse local folders",
      browseTitle: "Local folder browser",
      browseRoot: "This PC",
      up: "Up",
      useFolder: "Use this folder",
      noChildren: "No child directories found here.",
      test: "Test connection",
      reconnect: "Reconnect",
      scan: "Scan source",
      save: "Save source",
      localPlaceholder: "C:\\Videos\\Test Library",
      remotePlaceholder: "Accessible path or UNC share",
      portPlaceholder: "Default",
      keepPassword: "Leave blank to keep saved password",
      favorites: "Suggested local folders",
      testArchive: "Repo test archive",
      backendFolder: "Backend folder",
      backendData: "Backend local data",
      useSuggestion: "Use {{label}}",
      ready: "Ready to scan",
      partial: "Connection partial"
    },
    previewSettings: {
      intro:
        "Preview generation stays independent from conversion. Save the sampling and large-tile rules here, then use the live preview to inspect the layout before launching jobs.",
      sampleCount: "Sample count",
      largeTileCount: "Large tile count",
      timelineFlow: "Timeline flow",
      identityDiversity: "Identity diversity",
      savedPreset: "Saved preset",
      presetName: "Preset name",
      loadPreset: "Load preset",
      savePreset: "Save as new preset",
      updatePreset: "Update preset",
      saveSettings: "Save preview settings",
      aspectRatio: "Aspect ratio",
      rulesTitle: "Selection rules",
      rulesBody:
        "First two large tiles prefer faces. Remaining large tiles prefer figures. When identity diversity is enabled, the backend falls back to separate timeline regions if a full identity pass is too expensive.",
      livePreview: "Live preview",
      generating: "Generating layout preview...",
      row: "Row by row",
      column: "Column by column",
      shuffle: "Shuffled time order",
      square: "Square 1:1",
      video: "Classic 16:9",
      portrait: "Portrait 4:5",
      s24: "Samsung S24 portrait 9:19.5",
      ultrawide: "Ultrawide 21:9"
    },
    playbackSettings: {
      intro:
        "Playback mode is configurable because embedded viewing and external opening behave differently across machines and browser environments.",
      mode: "Playback mode",
      strategy: "External strategy",
      save: "Save playback settings",
      current: "Current behavior",
      currentBody:
        "Embedded playback streams through the backend. External playback opens the resolved file URI when the local environment supports it.",
      embedded: "Embedded modal playback",
      external: "External open",
      fileUri: "File URI / link",
      path: "Path-first"
    },
    taggingSettings: {
      intro:
        "Tagging stays separate from conversion and preview. The backend only stores tags selected from this allowed vocabulary plus confidence scores.",
      provider: "Provider",
      sampleCount: "Sample count",
      combine: "Combine frames",
      preferBatch: "Prefer batch",
      vocabulary: "Allowed vocabulary",
      vocabularyPlaceholder: "One tag per line",
      save: "Save tagging settings",
      closedTitle: "Closed vocabulary only",
      closedBody: "The model can only return tags from this list. Any out-of-vocabulary labels are discarded before storage."
    },
    providerSettings: {
      intro:
        "Configure backend-only provider access here. API keys stay out of the main metadata database and are stored separately.",
      enabled: "Enabled",
      visionModel: "Vision model",
      textModel: "Text model",
      apiKey: "API key",
      preferBatch: "Prefer batch",
      save: "Save provider settings",
      keyStored: "API key stored",
      keyMissing: "API key not stored",
      textPlaceholder: "Optional"
    },
    profiles: {
      intro: "Profiles stay reusable and separate from tuning runs. Tuning can promote a winning output here later.",
      create: "Create profile",
      saved: "Saved profiles",
      name: "Name",
      codec: "Codec",
      maxDimension: "Max dimension",
      qualityValue: "Quality value",
      dropAudio: "Drop audio",
      defaultProfile: "Default profile",
      advancedArgs: "Advanced encoder args",
      saveProfile: "Save profile",
      advancedPlaceholder: "Optional ffmpeg encoder args",
      optional: "Optional"
    },
    details: {
      kicker: "Video details",
      titleFallback: "Selected file",
      noPreview: "No file preview stored yet.",
      actions: "File actions",
      summary: "Quick facts",
      playback: "Playback",
      openPlayback: "Open and play",
      convert: "Convert file",
      preview: "Preview file",
      tag: "Tag file",
      tune: "Tune file",
      logs: "Filter logs",
      activity: "Recent file activity",
      noEvents: "No file-specific events yet.",
      relativePath: "Relative path",
      absolutePath: "Absolute path",
      size: "Size",
      modified: "Modified",
      discovered: "Discovered",
      convertState: "Convert state",
      previewState: "Preview state",
      lastConverted: "Last converted",
      previewGenerated: "Preview generated",
      assignedTags: "Assigned tags",
      noTags: "No tags stored yet.",
      loadingTitle: "Loading file details",
      loadingBody: "Fetching metadata, preview, tags, and recent file activity."
    },
    jobs: {
      kicker: "Tasks and jobs",
      title: "Recent jobs",
      noSummary: "No summary available.",
      itemsProgress: "Items {{completed}}/{{total}}",
      detail: "Job detail",
      refresh: "Refresh",
      cancel: "Cancel",
      restart: "Restart",
      openLogs: "Open in logs",
      queued: "Queued",
      running: "Running",
      completed: "Completed",
      failed: "Failed",
      cancelled: "Cancelled",
      items: "Items",
      events: "Events",
      noEvents: "No events yet.",
      noSelectionTitle: "No job selected",
      noSelectionBody: "Select a job to inspect its items and event stream.",
      noJobsTitle: "No jobs yet",
      noJobsBody: "Queued scan, rescan, convert, preview, tag, and tune jobs will appear here.",
      scopeItem: "Scope item"
    },
    logs: {
      kicker: "Log viewer",
      title: "Near-real-time backend activity",
      jobId: "Job id",
      fileId: "File id",
      level: "Level",
      clear: "Clear filters",
      empty: "No events match the current filters.",
      debug: "Debug",
      info: "Info",
      warning: "Warning",
      error: "Error"
    },
    tune: {
      kicker: "Tuning workflow",
      back: "Back to details",
      intro: "Tuning always creates separate outputs. It never replaces the source file and is limited to one video at a time.",
      dimensions: "Dimension sweep",
      qualities: "Quality sweep",
      codecs: "Codec sweep",
      dropAudio: "Drop audio",
      run: "Start tuning run",
      outputs: "Generated outputs",
      noRun: "No tuning run started yet.",
      saveProfile: "Save as profile",
      noOutputsTitle: "No tuning outputs yet",
      noOutputsBody: "Run a sweep to compare separate dimension, quality, and codec outputs.",
      events: "Run events",
      noEvents: "No tuning events yet."
    },
    playbackModal: {
      kicker: "Playback",
      target: "Playback target",
      openInfo: "Show file info"
    },
    conversionModal: {
      kicker: "Conversion",
      fileTitle: "Selected file",
      directoryTitle: "Selected folder",
      description:
        "Production mode writes a temp file, validates it quickly, and replaces the source only on success. Test mode writes a separate output and preserves the source file.",
      savedProfile: "Saved profile",
      mode: "Mode",
      production: "Production replace source",
      test: "Test keep source",
      start: "Start conversion"
    },
    promotion: {
      kicker: "Promote result",
      title: "Save tuning output as profile",
      name: "Profile name",
      markDefault: "Mark default",
      sourceDimension: "source",
      defaultQuality: "default quality",
      save: "Save profile"
    },
    messages: {
      sourceSaved: "Source settings saved.",
      previewSaved: "Preview settings saved.",
      playbackSaved: "Playback settings saved.",
      taggingSaved: "Tagging settings saved.",
      providersSaved: "Provider settings saved.",
      presetUpdated: "Preview preset updated.",
      presetSaved: "Preview preset saved.",
      noProfiles: "No saved conversion profiles are available.",
      externalPlayback: "Requested external playback for {{name}}.",
      profileSaved: "Saved conversion profile {{name}}.",
      tuningProfileSaved: "Saved profile {{name}} from tuning result."
    },
    status: {
      not_started: "not started",
      in_progress: "in progress",
      running: "running",
      queued: "queued",
      done: "done",
      completed: "completed",
      failed: "failed",
      cancelled: "cancelled",
      skipped: "skipped"
    },
    jobTypes: {
      scan: "Scan",
      rescan: "Rescan",
      convert: "Convert",
      preview: "Preview",
      tag: "Tag",
      tune: "Tune"
    }
  },
  ru: {
    app: {
      title: "Библиотека",
      brand: "Video Archive",
      summary:
        "Просматривайте один активный источник, держите главный экран лёгким, а воспроизведение, тюнинг, логи и глубокие действия по файлам выносите в отдельные модальные потоки.",
      noActiveSource: "Активный источник не настроен",
      queueSummary: "{{running}} выполняется - {{queued}} в очереди",
      queueRuntime: "Очередь: {{status}}",
      backendReady: "Бэкенд {{status}}",
      backendLoading: "Подключение к бэкенду",
      backendOffline: "Бэкенд недоступен",
      lastBackendError: "Последняя ошибка бэкенда: {{message}}",
      activeSource: "Активный источник",
      libraryRoot: "Корень библиотеки",
      sourceRoot: "Корень источника"
    },
    common: {
      close: "Закрыть",
      cancel: "Отмена",
      save: "Сохранить",
      refresh: "Обновить",
      open: "Открыть",
      loading: "Загрузка...",
      default: "По умолчанию",
      none: "-",
      allLevels: "Все уровни"
    },
    header: {
      source: "Источник",
      queue: "Очередь",
      togglePreviewShow: "Показать превью",
      togglePreviewHide: "Скрыть превью",
      scanSource: "Сканировать источник",
      logs: "Логи",
      jobs: "Задачи",
      settings: "Настройки",
      locale: "Язык",
      theme: "Визуальный режим"
    },
    theme: {
      strict: "Строгий",
      playful: "Игривый",
      casino: "Казино"
    },
    directory: {
      kicker: "Директории",
      title: "Дерево",
      rescanSource: "Пересканировать источник",
      emptyTitle: "Дерево ещё не просканировано",
      emptyBody: "Сохраните активный источник, затем запустите сканирование, чтобы заполнить дерево директорий.",
      convertBadge: "конверт",
      previewBadge: "превью"
    },
    files: {
      kicker: "Текущая папка",
      intro: "Основная панель остаётся сфокусированной на действиях по поддереву и лёгких входах в файлы.",
      details: "Детали",
      playback: "Плеер",
      backToParent: "На уровень выше",
      folderCard: "Папка",
      convertSubtree: "Конверт. поддерево",
      previewSubtree: "Превью поддерева",
      tagSubtree: "Теги поддерева",
      rescanSubtree: "Перескан. поддерево",
      emptyTitle: "В этой папке пока пусто",
      emptyBody: "Здесь пока не видно ни папок, ни файлов, либо сканирование их ещё не обнаружило.",
      name: "Имя",
      type: "Тип",
      size: "Размер",
      modified: "Изменён",
      status: "Статус",
      convertState: "Конверт {{state}}",
      previewState: "Превью {{state}}"
    },
    previewPanel: {
      kicker: "Превью",
      directoryTitle: "Коллаж директории",
      fileTitle: "Выбранный файл",
      settings: "Настройки превью",
      empty: "Превью ещё нет. Запустите задачу превью по файлу или поддереву.",
      summary:
        "{{sampleCount}} кадров, {{largeTileCount}} крупных плиток, порядок {{timelineFlow}}.",
      fallbackSummary: "Превью генерируется по запросу и остаётся отдельным потоком от конвертации и тегов.",
      selectedFolder: "Выбранная папка",
      visibleFiles: "Видимых файлов",
      selectedFile: "Выбранный файл",
      assignedTags: "Назначенных тегов",
      sampleCount: "Кадров",
      playbackMode: "Режим плеера",
      aspectRatio: "Соотношение сторон",
      closedVocabulary: "Теги из закрытого словаря",
      noTags: "Для выбранного видео пока нет тегов. Запустите задачу тегирования."
    },
    settings: {
      title: "Настройки",
      source: "Источник",
      profiles: "Профили",
      preview: "Превью",
      playback: "Плеер",
      tagging: "Теги",
      providers: "Провайдеры",
      backup: "Бэкап",
      maintenance: "Обслуживание",
      secondaryFlow: "Этот раздел остаётся вторичным обслуживающим потоком и не выводится на главный экран библиотеки."
    },
    sourceSettings: {
      intro:
        "Video Archive поддерживает один активный источник одновременно. Используйте удалённый протокол для серверных библиотек или переключайтесь на локальную папку, когда хотите тестировать прямо на этой машине.",
      name: "Имя",
      protocol: "Протокол",
      rootPath: "Корневая папка",
      host: "Хост",
      port: "Порт",
      username: "Пользователь",
      password: "Пароль",
      localOption: "Локальная папка",
      browse: "Открыть локальные папки",
      browseTitle: "Навигатор локальных папок",
      browseRoot: "Этот компьютер",
      up: "Вверх",
      useFolder: "Выбрать эту папку",
      noChildren: "Здесь нет дочерних директорий.",
      test: "Проверить соединение",
      reconnect: "Переподключить",
      scan: "Сканировать источник",
      save: "Сохранить источник",
      localPlaceholder: "C:\\Videos\\Test Library",
      remotePlaceholder: "Доступный путь или UNC-шара",
      portPlaceholder: "По умолчанию",
      keepPassword: "Оставьте пустым, чтобы сохранить текущий пароль",
      favorites: "Рекомендуемые локальные папки",
      testArchive: "Тестовый архив в репозитории",
      backendFolder: "Папка backend",
      backendData: "Локальные данные backend",
      useSuggestion: "Использовать {{label}}",
      ready: "Готово к сканированию",
      partial: "Соединение частично готово"
    },
    previewSettings: {
      intro:
        "Генерация превью остаётся независимой от конвертации. Сохраните здесь правила выборки и крупных плиток, затем смотрите live preview перед запуском задач.",
      sampleCount: "Количество кадров",
      largeTileCount: "Крупных плиток",
      timelineFlow: "Порядок по времени",
      identityDiversity: "Разнообразие лиц",
      savedPreset: "Сохранённый пресет",
      presetName: "Имя пресета",
      loadPreset: "Загрузить пресет",
      savePreset: "Сохранить как новый",
      updatePreset: "Обновить пресет",
      saveSettings: "Сохранить настройки превью",
      aspectRatio: "Соотношение сторон",
      rulesTitle: "Правила отбора",
      rulesBody:
        "Первые две крупные плитки предпочитают лица. Остальные крупные плитки предпочитают фигуры. Когда включено разнообразие лиц, бэкенд может переходить к разным временным сегментам, если полный проход слишком дорогой.",
      livePreview: "Live preview",
      generating: "Генерация макета...",
      row: "По строкам",
      column: "По колонкам",
      shuffle: "Перемешанный порядок",
      square: "Квадрат 1:1",
      video: "Классика 16:9",
      portrait: "Портрет 4:5",
      s24: "Samsung S24 портрет 9:19.5",
      ultrawide: "Ультраширокий 21:9"
    },
    playbackSettings: {
      intro:
        "Режим воспроизведения настраивается, потому что встроенный просмотр и внешнее открытие ведут себя по-разному на разных машинах и в разных браузерных окружениях.",
      mode: "Режим плеера",
      strategy: "Стратегия внешнего открытия",
      save: "Сохранить настройки плеера",
      current: "Текущее поведение",
      currentBody:
        "Встроенный режим стримит через бэкенд. Внешний режим открывает разрешённый file URI, когда локальная среда это поддерживает.",
      embedded: "Встроенный модальный плеер",
      external: "Внешнее открытие",
      fileUri: "File URI / ссылка",
      path: "Сначала путь"
    },
    taggingSettings: {
      intro:
        "Тегирование остаётся отдельным от конвертации и превью. Бэкенд сохраняет только теги из этого разрешённого словаря вместе с confidence.",
      provider: "Провайдер",
      sampleCount: "Количество кадров",
      combine: "Объединять кадры",
      preferBatch: "Предпочитать batch",
      vocabulary: "Разрешённый словарь",
      vocabularyPlaceholder: "Один тег на строку",
      save: "Сохранить настройки тегов",
      closedTitle: "Только закрытый словарь",
      closedBody: "Модель может вернуть только теги из этого списка. Любые внешние метки отбрасываются до сохранения."
    },
    providerSettings: {
      intro:
        "Здесь настраивается доступ к провайдерам только для backend. API keys не попадают в основную metadata database и хранятся отдельно.",
      enabled: "Включён",
      visionModel: "Vision model",
      textModel: "Text model",
      apiKey: "API key",
      preferBatch: "Предпочитать batch",
      save: "Сохранить провайдеров",
      keyStored: "API key сохранён",
      keyMissing: "API key не сохранён",
      textPlaceholder: "Опционально"
    },
    profiles: {
      intro: "Профили остаются переиспользуемыми и отдельными от тюнинга. Позже удачный результат тюнинга можно поднять сюда.",
      create: "Создать профиль",
      saved: "Сохранённые профили",
      name: "Имя",
      codec: "Кодек",
      maxDimension: "Макс. размер",
      qualityValue: "Значение качества",
      dropAudio: "Убрать аудио",
      defaultProfile: "Профиль по умолчанию",
      advancedArgs: "Доп. аргументы кодера",
      saveProfile: "Сохранить профиль",
      advancedPlaceholder: "Опциональные ffmpeg аргументы",
      optional: "Опционально"
    },
    details: {
      kicker: "Детали видео",
      titleFallback: "Выбранный файл",
      noPreview: "Превью файла ещё не сохранено.",
      actions: "Действия с файлом",
      summary: "Краткая сводка",
      playback: "Плеер",
      openPlayback: "Открыть и воспроизвести",
      convert: "Конвертировать файл",
      preview: "Сделать превью",
      tag: "Проставить теги",
      tune: "Тюнинг",
      logs: "Отфильтр. логи",
      activity: "Последняя активность по файлу",
      noEvents: "Событий по файлу пока нет.",
      relativePath: "Относительный путь",
      absolutePath: "Абсолютный путь",
      size: "Размер",
      modified: "Изменён",
      discovered: "Обнаружен",
      convertState: "Статус конвертации",
      previewState: "Статус превью",
      lastConverted: "Последняя конвертация",
      previewGenerated: "Превью создано",
      assignedTags: "Назначенные теги",
      noTags: "Тегов пока нет.",
      loadingTitle: "Загрузка деталей файла",
      loadingBody: "Подтягиваются метаданные, превью, теги и последняя активность."
    },
    jobs: {
      kicker: "Задачи и джобы",
      title: "Последние задачи",
      noSummary: "Краткого описания пока нет.",
      itemsProgress: "Элементы {{completed}}/{{total}}",
      detail: "Детали задачи",
      refresh: "Обновить",
      cancel: "Отменить",
      restart: "Перезапустить",
      openLogs: "Открыть в логах",
      queued: "В очереди",
      running: "В работе",
      completed: "Готово",
      failed: "Ошибки",
      cancelled: "Отменено",
      items: "Элементы",
      events: "События",
      noEvents: "Событий пока нет.",
      noSelectionTitle: "Задача не выбрана",
      noSelectionBody: "Выберите задачу, чтобы посмотреть её элементы и поток событий.",
      noJobsTitle: "Задач пока нет",
      noJobsBody: "Здесь появятся scan, rescan, convert, preview, tag и tune задачи.",
      scopeItem: "Элемент области"
    },
    logs: {
      kicker: "Просмотр логов",
      title: "Почти realtime активность backend",
      jobId: "Job id",
      fileId: "File id",
      level: "Уровень",
      clear: "Сбросить фильтры",
      empty: "Под текущие фильтры ничего не попало.",
      debug: "Debug",
      info: "Info",
      warning: "Warning",
      error: "Error"
    },
    tune: {
      kicker: "Поток тюнинга",
      back: "Назад к деталям",
      intro: "Тюнинг всегда создаёт отдельные результаты. Он никогда не заменяет исходный файл и работает только по одному видео за раз.",
      dimensions: "Размеры",
      qualities: "Качество",
      codecs: "Кодеки",
      dropAudio: "Убрать аудио",
      run: "Запустить тюнинг",
      outputs: "Сгенерированные результаты",
      noRun: "Тюнинг ещё не запускался.",
      saveProfile: "Сохранить как профиль",
      noOutputsTitle: "Результатов тюнинга пока нет",
      noOutputsBody: "Запустите sweep, чтобы сравнить разные размеры, качество и кодеки.",
      events: "События запуска",
      noEvents: "Событий тюнинга пока нет."
    },
    playbackModal: {
      kicker: "Воспроизведение",
      target: "Цель воспроизведения",
      openInfo: "Показать сведения о файле"
    },
    conversionModal: {
      kicker: "Конвертация",
      fileTitle: "Выбранный файл",
      directoryTitle: "Выбранная папка",
      description:
        "Режим production пишет временный файл, быстро валидирует его и заменяет исходник только при успехе. Режим test пишет отдельный результат и сохраняет исходный файл.",
      savedProfile: "Сохранённый профиль",
      mode: "Режим",
      production: "Production: заменить источник",
      test: "Test: сохранить источник",
      start: "Запустить конвертацию"
    },
    promotion: {
      kicker: "Поднять результат",
      title: "Сохранить результат тюнинга как профиль",
      name: "Имя профиля",
      markDefault: "Сделать по умолчанию",
      sourceDimension: "источник",
      defaultQuality: "качество по умолчанию",
      save: "Сохранить профиль"
    },
    messages: {
      sourceSaved: "Настройки источника сохранены.",
      previewSaved: "Настройки превью сохранены.",
      playbackSaved: "Настройки плеера сохранены.",
      taggingSaved: "Настройки тегов сохранены.",
      providersSaved: "Настройки провайдеров сохранены.",
      presetUpdated: "Пресет превью обновлён.",
      presetSaved: "Пресет превью сохранён.",
      noProfiles: "Нет сохранённых профилей конвертации.",
      externalPlayback: "Запрошено внешнее воспроизведение для {{name}}.",
      profileSaved: "Профиль конвертации {{name}} сохранён.",
      tuningProfileSaved: "Профиль {{name}} сохранён из результата тюнинга."
    },
    status: {
      not_started: "не начат",
      in_progress: "в процессе",
      running: "в работе",
      queued: "в очереди",
      done: "готово",
      completed: "завершено",
      failed: "ошибка",
      cancelled: "отменено",
      skipped: "пропущено"
    },
    jobTypes: {
      scan: "Скан",
      rescan: "Перескан",
      convert: "Конвертация",
      preview: "Превью",
      tag: "Теги",
      tune: "Тюнинг"
    }
  }
}

Object.assign(messages.en.header, {
  search: "Search library",
  searchPlaceholder: "Search folders and videos"
})

Object.assign(messages.ru.header, {
  search: "\u041f\u043e\u0438\u0441\u043a",
  searchPlaceholder: "\u041f\u043e\u0438\u0441\u043a \u043f\u0430\u043f\u043e\u043a \u0438 \u0432\u0438\u0434\u0435\u043e"
})

Object.assign(messages.en.files, {
  convertSubtree: "Convert",
  previewSubtree: "Preview",
  tagSubtree: "Tag",
  rescanSubtree: "Rescan",
  runTask: "Run selected task",
  searchEmptyTitle: "Nothing matched the search",
  searchEmptyBody: "Try a shorter name or clear the search field in the top bar."
})

Object.assign(messages.ru.files, {
  convertSubtree: "\u041a\u043e\u043d\u0432\u0435\u0440\u0442\u0430\u0446\u0438\u044f",
  previewSubtree: "\u041f\u0440\u0435\u0432\u044c\u044e",
  tagSubtree: "\u0422\u0435\u0433\u0438",
  rescanSubtree: "\u041f\u0435\u0440\u0435\u0441\u043a\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
  runTask: "\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0437\u0430\u0434\u0430\u0447\u0443",
  searchEmptyTitle: "\u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e",
  searchEmptyBody: "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043e\u043a\u0440\u0430\u0442\u0438\u0442\u044c \u0437\u0430\u043f\u0440\u043e\u0441 \u0438\u043b\u0438 \u043e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u043f\u043e\u0438\u0441\u043a \u0432 \u0432\u0435\u0440\u0445\u043d\u0435\u0439 \u043f\u043e\u043b\u043e\u0441\u0435."
})

Object.assign(messages.en.details, {
  previewAsset: "Stored preview asset",
  previewFileName: "Preview file",
  previewFilePath: "Preview path"
})

Object.assign(messages.ru.details, {
  previewAsset: "\u0421\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u043e\u0435 \u043f\u0440\u0435\u0432\u044c\u044e",
  previewFileName: "\u0424\u0430\u0439\u043b \u043f\u0440\u0435\u0432\u044c\u044e",
  previewFilePath: "\u041f\u0443\u0442\u044c \u043a \u043f\u0440\u0435\u0432\u044c\u044e"
})

function resolveMessage(locale, key) {
  return key.split(".").reduce((current, part) => current?.[part], messages[locale]) ?? key
}

export function createTranslator(locale) {
  return (key, params = {}) => {
    const template = resolveMessage(locale, key)
    return Object.entries(params).reduce(
      (result, [paramKey, value]) => result.replaceAll(`{{${paramKey}}}`, String(value)),
      String(template)
    )
  }
}

export function getSettingsSections(t) {
  return [
    { id: "source", label: t("settings.source") },
    { id: "profiles", label: t("settings.profiles") },
    { id: "preview", label: t("settings.preview") },
    { id: "playback", label: t("settings.playback") },
    { id: "tagging", label: t("settings.tagging") },
    { id: "providers", label: t("settings.providers") },
    { id: "backup", label: t("settings.backup") },
    { id: "maintenance", label: t("settings.maintenance") }
  ]
}

export const visualModes = ["strict", "playful", "casino"]
