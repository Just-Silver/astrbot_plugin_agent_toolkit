import { existsSync, renameSync } from 'node:fs'
import { resolve } from 'node:path'

// AstrBot discovers a plugin view by <views>/<name>/index.html, while Vite keeps
// the HTML entry's file name. Rename the built entry to satisfy that contract.
const directory = resolve(process.cwd(), '../views/hotfix')
const source = resolve(directory, 'hotfix.html')
const target = resolve(directory, 'index.html')

if (existsSync(source)) {
  renameSync(source, target)
}
