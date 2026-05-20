import { createApp } from 'vue'
import {
  FrappeUI,
  setConfig,
  frappeRequest,
  resourcesPlugin,
} from 'frappe-ui'

import App from './App.vue'
import router from './router'

setConfig('resourceFetcher', frappeRequest)

const app = createApp(App)
app.use(router)
app.use(FrappeUI)
app.use(resourcesPlugin)
app.mount('#app')
