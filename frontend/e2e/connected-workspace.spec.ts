import { expect,test } from '@playwright/test'
async function login(page:import('@playwright/test').Page){await page.goto('/login');await page.getByRole('button',{name:/Enter AdviCue/}).click();await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible()}
test('home has greeting, dynamic counts and local AI search; Reviews is second',async({page})=>{
 await login(page);await expect(page.locator('h1')).toHaveText(/Good (morning|afternoon|evening)/);await expect(page.getByLabel('Your client book')).toContainText('20');await expect(page.getByLabel('Ask AdviCue AI')).toBeVisible();await expect(page.getByRole('button',{name:'Which clients need my attention?'})).toBeVisible()
 const nav=page.getByRole('navigation',{name:'Main navigation'}).getByRole('link');await expect(nav).toHaveCount(7);await expect(nav.nth(0)).toHaveText('Home');await expect(nav.nth(1)).toHaveText('Reviews');await expect(page.getByRole('navigation').getByRole('link',{name:'Pattern detection',exact:true})).toBeVisible();await page.screenshot({path:'../docs/screenshots/v6-home.png',fullPage:true})
 await nav.nth(1).click();await expect(page.locator('.focus-count-strip')).toHaveCount(0);await expect(page.getByRole('link',{name:'Shared patterns',exact:true})).toHaveCount(0);await expect(page.getByRole('heading',{name:'Who needs attention?'})).toBeVisible()
})
test('home AI search opens a scoped client record',async({page})=>{
 test.setTimeout(60000);await login(page);await page.getByLabel('Ask AdviCue AI').fill('Show INV0009 portfolio');await page.getByRole('button',{name:'Search with AdviCue AI'}).click();await expect(page.locator('.home-result-card').first()).toBeVisible({timeout:45000});await expect(page.locator('.home-result-card').first()).toContainText('Sanya Malhotra');await expect(page.locator('.home-results')).not.toContainText('INV0048');await page.locator('.home-result-card').first().click();await expect(page).toHaveURL(/investors\?selected=INV0009/)
})
test('follow-ups show names and open a dedicated record at the top',async({page})=>{
 await login(page);const tasks=(await (await page.request.get('/api/v1/tasks')).json()).items;expect(tasks.length).toBeGreaterThan(0);const task=tasks[0]
 await page.goto('/advice/follow-ups');await expect(page.locator('.v6-followup-table')).toContainText(task.investor_name);await expect(page.locator('.v6-followup-table')).not.toContainText(task.investor_id);await page.getByRole('link',{name:'Open follow-up',exact:true}).first().click();await expect(page).toHaveURL(/advice\/follow-ups\/[\w-]+$/);await expect(page.getByRole('heading',{name:task.investor_name,exact:true})).toBeVisible();await expect(page.locator('.v6-followup-table')).toHaveCount(0);expect(await page.evaluate(()=>window.scrollY)).toBeLessThan(100);await page.screenshot({path:'../docs/screenshots/v6-follow-up-detail.png',fullPage:true})
})
test('create follow-up opens its own page inside Advice',async({page})=>{
 await login(page);const advice=(await (await page.request.get('/api/v1/advice')).json()).items.find((a:{status:string})=>a.status==='APPROVED');expect(advice).toBeTruthy();await page.goto('/advice/'+advice.id);await page.getByRole('link',{name:'Create follow-up →'}).click();await expect(page).toHaveURL(/advice\/follow-ups\/new\?advice=/);await expect(page.getByLabel('Follow-up action')).toBeVisible();await expect(page.locator('.v6-followup-table')).toHaveCount(0);await expect(page.getByRole('heading',{name:advice.investor_name,exact:true})).toBeVisible()
})
test('all pages remain readable and fit desktop and mobile widths',async({page})=>{
 test.setTimeout(90000);await page.setViewportSize({width:1440,height:1000});await login(page)
 for(const [url,name] of [['/','home'],['/attention','reviews'],['/investors','clients'],['/patterns','patterns'],['/advice','advice'],['/advice/follow-ups','follow-ups'],['/local-ai','meetings'],['/data-trust','data'],['/pilot','pilot'],['/activity','history'],['/investors?selected=INV0009','client']]){
  await page.goto(url);await page.waitForLoadState('networkidle');await expect(page.locator('h1')).toBeVisible();await expect(page.locator('[role="alert"]')).toHaveCount(0);await page.screenshot({path:`../docs/screenshots/v6-${name}.png`,fullPage:true,animations:'disabled'});await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),{message:name+' mobile overflow'}).toBeTruthy();await page.screenshot({path:`../docs/screenshots/v6-${name}-mobile.png`,fullPage:true,animations:'disabled'});await page.setViewportSize({width:1440,height:1000})
 }
})
test('client workspace separates source-reviewed performance, goals and history',async({page})=>{
 await login(page);await page.goto('/investors?selected=INV0009');await expect(page.getByRole('tab')).toHaveCount(4);await page.getByRole('tab',{name:'Performance',exact:true}).click();await expect(page.getByText('Reviewed financial evidence is needed',{exact:true})).toBeVisible();await page.getByText('Add or review financial evidence',{exact:true}).click();await expect(page.getByLabel('Upload financial evidence')).toBeVisible();await page.getByRole('tab',{name:'Goals',exact:true}).click();await expect(page.getByLabel('Annual return assumptions %')).toBeVisible();await page.getByRole('tab',{name:'Advice & notes'}).click();await expect(page.getByRole('heading',{name:'Advice, meetings & follow-ups'})).toBeVisible()
})
test('CSV connections, calendar export and real pilot controls are accessible',async({page})=>{
 await login(page);await page.goto('/data-trust');await expect(page.getByLabel('Import holdings CSV')).toBeVisible();expect((await page.request.get('/api/v1/connections/holdings-template.csv')).ok()).toBeTruthy();expect((await page.request.get('/api/v1/connections/follow-ups.ics')).headers()['content-type']).toContain('text/calendar');await page.goto('/pilot');await expect(page.getByRole('button',{name:'Start random unflagged review'})).toBeVisible();await expect(page.getByText('Not measured',{exact:true}).first()).toBeVisible()
})
test('20 assigned demo clients and access boundaries remain intact',async({page})=>{
 await login(page);await page.goto('/investors');await expect(page.locator('tbody tr')).toHaveCount(20);for(const suffix of ['analysis','evidence','verified-analysis','timeline'])expect((await page.request.get('/api/v1/investors/INV0048/'+suffix)).status()).toBe(404)
})

test('approved meeting evidence remains linked in a new advice draft',async({page})=>{
 await login(page);const notes=(await (await page.request.get('/api/v1/meetings')).json()).items;const note=notes.find((n:{status:string})=>n.status==='APPROVED');expect(note).toBeTruthy();await page.goto('/advice?meeting_note='+encodeURIComponent(note.id));await expect(page.getByLabel('Approved meeting evidence (optional)')).toHaveValue(note.id);await expect(page.getByRole('heading',{name:'Agree on the next step'})).toBeVisible();await expect(page.getByRole('combobox',{name:'Client review',exact:true})).not.toHaveValue('')
})
