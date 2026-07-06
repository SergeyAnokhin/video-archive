import { AppLayout } from './components/AppLayout'
import { ConversionProfilesProvider } from './context/ConversionProfilesContext'
import { JobsProvider } from './context/JobsContext'
import { PreviewVisibilityProvider } from './context/PreviewVisibilityContext'
import { SourceProvider } from './context/SourceContext'

function App() {
  return (
    <PreviewVisibilityProvider>
      <SourceProvider>
        <ConversionProfilesProvider>
          <JobsProvider>
            <AppLayout />
          </JobsProvider>
        </ConversionProfilesProvider>
      </SourceProvider>
    </PreviewVisibilityProvider>
  )
}

export default App
