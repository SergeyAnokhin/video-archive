import { AppLayout } from './components/AppLayout'
import { PreviewVisibilityProvider } from './context/PreviewVisibilityContext'
import { SourceProvider } from './context/SourceContext'

function App() {
  return (
    <PreviewVisibilityProvider>
      <SourceProvider>
        <AppLayout />
      </SourceProvider>
    </PreviewVisibilityProvider>
  )
}

export default App
