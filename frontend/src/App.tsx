import { AppLayout } from './components/AppLayout'
import { JobsProvider } from './context/JobsContext'
import { PreviewVisibilityProvider } from './context/PreviewVisibilityContext'
import { SourceProvider } from './context/SourceContext'

function App() {
  return (
    <PreviewVisibilityProvider>
      <SourceProvider>
        <JobsProvider>
          <AppLayout />
        </JobsProvider>
      </SourceProvider>
    </PreviewVisibilityProvider>
  )
}

export default App
