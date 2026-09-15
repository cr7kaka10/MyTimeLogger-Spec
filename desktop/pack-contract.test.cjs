const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')

const pkg = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf8'))
if (!pkg.scripts.pack.includes('npm --prefix ../ui run build:android-web')) throw new Error('Desktop pack must build fresh UI staging')
const ui = pkg.build.extraResources.find(item => item.from === '../ui/dist')
if (!ui || ui.to !== 'ui/dist' || !ui.filter.includes('**/*')) throw new Error('Desktop pack must consume staged UI dist')
console.log('desktop pack contract passed')
