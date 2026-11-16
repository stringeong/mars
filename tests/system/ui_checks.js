// 화면 케이스 6개를 Playwright(headless Chromium)로 수행하고 화면을 캡처한다.
// systest.py가 실행 중에 만든 상태 파일(토큰, 워크플로우·실행 id)을 받아 결과를 JSON으로 돌려준다.
//
//   node tests/system/ui_checks.js <상태 파일> <결과 파일>
//
// 준비: cd tests/system && npm install && npx playwright install chromium
const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')

const [statePath, outPath] = process.argv.slice(2)
const state = JSON.parse(fs.readFileSync(statePath, 'utf-8'))
const shots = state.screenshot_dir
fs.mkdirSync(shots, { recursive: true })
const results = {}

async function run(id, page, fn) {
  try {
    const { ok, actual } = await fn()
    results[id] = { ok, actual }
  } catch (error) {
    results[id] = { ok: false, actual: `예외: ${error.message.split('\n')[0]}` }
  }
  await page.screenshot({ path: path.join(shots, `${id}.png`), fullPage: true }).catch(() => {})
  console.log(`[${results[id].ok ? 'P' : 'F'}] ${id} ${results[id].actual}`)
}

;(async () => {
  const browser = await chromium.launch()
  const anonymous = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  // 웹 앱은 로그인 토큰을 localStorage의 mars_token에 둔다
  await context.addInitScript((token) => localStorage.setItem('mars_token', token), state.token)
  const page = await context.newPage()

  await run('STC-T06-005', page, async () => {
    await page.goto(`${state.web_url}/services/${state.service_id}`)
    await page.locator('.react-flow__node').first().waitFor({ timeout: 20000 })
    await page.waitForTimeout(500)
    const blocks = await page.locator('.react-flow__node').count()
    const edges = await page.locator('.react-flow__edge').count()
    return { ok: blocks === 3 && edges === 2, actual: `블록 ${blocks}개, 연결선 ${edges}개 표시` }
  })

  await run('STC-T09-008', page, async () => {
    await page.goto(`${state.web_url}/executions/${state.run_id}`)
    await page.getByRole('button', { name: '간트 보기' }).click()
    await page.locator('.gantt-lane').first().waitFor({ timeout: 20000 })
    const lanes = await page.locator('.gantt-lane .gantt-lane-label').allInnerTexts()
    return { ok: lanes.length === 2, actual: `레인 ${lanes.length}개: ${lanes.join(', ')}` }
  })

  await run('STC-T10-003', page, async () => {
    await page.goto(`${state.web_url}/executions/${state.run_id}`)
    const box = page.locator('.final-result-card .result-box')
    await box.waitFor({ timeout: 20000 })
    const tables = await box.locator('table').count()
    const headings = await box.locator('h1, h2, h3, h4, h5, h6').count()
    // 렌더링되면 '## 제목'·'|---|' 같은 Markdown 기호가 화면에 그대로 보이지 않는다
    const raw = /(^|\n)#{1,6} |\|\s*-{3,}/.test(await box.innerText())
    return {
      ok: !raw && headings > 0,
      actual: `렌더링된 표 ${tables}개, 제목 요소 ${headings}개, Markdown 기호 원문 표시=${raw}`,
    }
  })

  await run('STC-T14-002', anonymous, async () => {
    await anonymous.goto(`${state.web_url}/`)
    const hero = anonymous.locator('h1', { hasText: '함께 일하는 AI 팀' })
    await hero.waitFor({ timeout: 20000 })
    const url = new URL(anonymous.url()).pathname
    return { ok: url === '/', actual: `비로그인 / 접속 시 제품 소개 표시=true, URL ${url}` }
  })

  await run('STC-T14-003', anonymous, async () => {
    await anonymous.goto(`${state.web_url}/download`)
    await anonymous.locator('main, body').first().waitFor()
    await anonymous.waitForTimeout(500)
    const text = await anonymous.locator('body').innerText()
    const server = text.includes(`${state.web_url}/api`)
    const os = ['Windows', 'macOS', 'Linux'].filter((name) => text.includes(name))
    return { ok: server && os.length === 3, actual: `서버 주소(/api) 표시=${server}, OS 안내 ${os.join('·')}` }
  })

  await run('STC-T14-004', anonymous, async () => {
    await anonymous.goto(`${state.web_url}/examples`)
    // 공유된 워크플로우가 있으면 '커뮤니티 공유' 탭으로 열리므로 추천 예시 탭을 고른다
    await anonymous.getByRole('tab', { name: /추천 예시/ }).click()
    const cards = anonymous.locator('.mk-examples > *')
    await cards.first().waitFor({ timeout: 20000 })
    const before = await cards.count()
    await anonymous.getByRole('searchbox', { name: '검색' }).fill('회의록')
    await anonymous.waitForTimeout(300)
    const after = await cards.count()
    const shown = (await anonymous.locator('.mk-examples').innerText()).includes('회의록')
    return { ok: after < before && after >= 1 && shown, actual: `검색 전 ${before}개 → '회의록' 검색 후 ${after}개` }
  })

  await browser.close()
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2))
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
