import { AppLayout } from './components/AppLayout'
import { ConversionProfilesProvider } from './context/ConversionProfilesContext'
import { JobsProvider } from './context/JobsContext'
import { PreviewVisibilityProvider } from './context/PreviewVisibilityContext'
import { SourceProvider } from './context/SourceContext'
import { TagsProvider } from './context/TagsContext'

function App() {
  return (
    <PreviewVisibilityProvider>
      <SourceProvider>
        <ConversionProfilesProvider>
          <TagsProvider>
            <JobsProvider>
              <AppLayout />
            </JobsProvider>
          </TagsProvider>
        </ConversionProfilesProvider>
      </SourceProvider>
    </PreviewVisibilityProvider>
  )
}

export default App
