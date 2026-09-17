import { test, expect } from '@playwright/test';
import { noHorizontalOverflow } from '../e2e/helpers';

test('browser-only demo saves edits, switches approvers, downloads and isolates visitors', async ({page, browser}, testInfo) => {
  const errors: string[] = [], apiRequests: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url());});
  await page.goto('./');
  await expect(page.locator('.album-header h1')).toHaveText('제주 여행');
  await expect(page.locator('.photo-card')).toHaveCount(12);
  await page.locator('.filter-pills').getByRole('button', {name: '함께', exact: true}).click();
  await expect(page.locator('.photo-card').first()).toBeVisible();
  const count = await page.locator('.photo-card').count(); expect(count).toBeGreaterThan(0); expect(count).toBeLessThan(12);
  await page.getByRole('button', {name: 'JEJU_0002.jpg 보정하기', exact: true}).click();
  const editor = page.getByRole('dialog', {name: '사진 보정 및 함께 고르기'});
  await editor.getByRole('slider', {name: '밝기'}).press('ArrowRight');
  await editor.getByLabel('새 보정본 이름').fill('팀원 체험 보정');
  await editor.getByRole('button', {name: '새 보정본 저장', exact: true}).click();
  await expect(editor.getByRole('heading', {name: '팀원 체험 보정', exact: true})).toBeVisible();
  await editor.getByRole('checkbox', {name: '사진의 등장 멤버와 승인 대상을 확인했어요.'}).check();
  await editor.getByRole('button', {name: '확인 요청 보내기'}).click();
  await editor.getByRole('button', {name: '이 보정본 승인', exact: true}).click();
  await expect(editor).toContainText('1 / 2명 승인');
  await page.getByLabel('체험 인물').selectOption('minji');
  await editor.getByRole('button', {name: '이 보정본 승인', exact: true}).click();
  await expect(editor).toContainText('2 / 2명 승인');
  await editor.getByRole('button', {name: '최종본으로 정하기'}).click();
  await expect(editor).toContainText('최종본으로 선택됨');
  await editor.locator('.editor-download summary').click();
  const downloading = page.waitForEvent('download');
  await editor.getByRole('button', {name: /최종본 다운로드/}).click();
  expect((await downloading).suggestedFilename()).toContain('-v1.jpg');
  await page.reload();
  await page.getByRole('button', {name: 'JEJU_0002.jpg 보정하기', exact: true}).click();
  await expect(page.locator('.editor-version.active')).toContainText('팀원 체험 보정');
  await expect(page.getByRole('slider', {name: '밝기'})).toHaveValue('1.01');
  await page.setViewportSize({width: 390, height: 844});
  await expect(page.locator('.editor-mobile-review')).toContainText('2 / 2명 승인');
  await noHorizontalOverflow(page);
  await expect(page.getByLabel('체험 인물')).toBeVisible();
  await page.getByRole('button', {name: '체험 · 이 브라우저에만 저장'}).click();
  const guide = page.getByRole('dialog', {name: '찍 체험 안내'});
  await expect(guide).toBeVisible();
  await guide.getByRole('button', {name: '닫기', exact: true}).click();
  await expect(editor).toBeVisible();
  await page.screenshot({path: testInfo.outputPath('demo-mobile-approval.png')});
  await page.locator('.editor-mobile-review').getByRole('button', {name: '내 승인 취소'}).click();
  await expect(page.locator('.editor-mobile-review')).toContainText('1 / 2명 승인');
  const separate = await browser.newContext();
  const other = await separate.newPage();
  await other.goto('http://127.0.0.1:5174/ZZIK/');
  await other.getByRole('button', {name: 'JEJU_0002.jpg 보정하기', exact: true}).click();
  await expect(other.locator('.editor-version')).toHaveCount(1);
  await separate.close();
  expect(apiRequests).toEqual([]); expect(errors).toEqual([]);
});

test('mobile demo uploads locally, reports analysis limits, and resets only its own data', async ({page}, testInfo) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('./');
  await expect(page.locator('.album-card')).toHaveCount(3);
  await page.locator('.album-card').first().click();
  await page.getByRole('button', {name: '사진 올리기', exact: true}).click();
  const upload = page.getByRole('dialog', {name: '사진 올리기'});
  await upload.getByLabel('업로드할 사진').setInputFiles('public/demo/photo-01.jpg');
  await upload.getByRole('button', {name: '사진 올리기', exact: true}).click();
  await expect(upload).toContainText('1장 저장 완료');
  await upload.getByRole('button', {name: '닫기', exact: true}).click();
  await expect(page.locator('.photo-card')).toHaveCount(13);
  await page.reload();
  await page.locator('.album-card').first().click();
  await expect(page.locator('.photo-card')).toHaveCount(13);
  await page.getByRole('button', {name: 'photo-01.jpg 사진 정보', exact: true}).click();
  await page.getByRole('navigation', {name: '사진 상세 메뉴'}).getByRole('button', {name: '사진 정보', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('체험 모드에서는 새 사진을 자동 분석하지 않아요.');
  await page.getByRole('button', {name: '사진 상세 닫기'}).click();
  await page.getByRole('button', {name: '체험 초기화', exact: true}).click();
  await page.getByRole('dialog').getByRole('button', {name: '체험 초기화', exact: true}).click();
  await expect(page.locator('.album-card')).toHaveCount(3);
  await page.locator('.album-card').first().click();
  await expect(page.locator('.photo-card')).toHaveCount(12);
  await noHorizontalOverflow(page);
  expect(await page.locator('img').evaluateAll(images => images.filter(image => image.complete && image.naturalWidth === 0).length)).toBe(0);
  await expect(page.getByLabel('체험 인물')).toBeVisible();
  await page.screenshot({path: testInfo.outputPath('demo-mobile-library.png')});
});

test('existing browser data gains nullable contract fields without losing photos', async ({page}) => {
  await page.goto('./');
  await expect(page.locator('.photo-card')).toHaveCount(12);
  await page.getByLabel('체험 인물').selectOption('minji');
  // Switching user persists the existing demo state; emulate the previous stored shape.
  await expect.poll(() => page.evaluate(() => new Promise<boolean>((resolve, reject) => {
    const opening = indexedDB.open('zzik-browser-demo-v1', 1);
    opening.onerror = () => reject(opening.error);
    opening.onsuccess = () => {
      const db = opening.result;
      const request = db.transaction('state').objectStore('state').get('current');
      request.onsuccess = () => { db.close(); resolve(Boolean(request.result)); };
      request.onerror = () => { db.close(); reject(request.error); };
    };
  }))).toBe(true);
  const before = await page.evaluate(() => new Promise<{photoId: string; count: number}>((resolve, reject) => {
    const opening = indexedDB.open('zzik-browser-demo-v1', 1);
    opening.onerror = () => reject(opening.error);
    opening.onsuccess = () => {
      const db = opening.result;
      const tx = db.transaction('state', 'readwrite');
      const store = tx.objectStore('state');
      const request = store.get('current');
      let summary: {photoId: string; count: number};
      request.onsuccess = () => {
        const state = request.result;
        summary = {photoId: state.photos[0].id, count: state.photos.length};
        for (const album of state.albums) {
          delete album.owner_id; delete album.cover_url;
          for (const person of album.people) delete person.proposed_user_id;
        }
        for (const photo of state.photos) {
          for (const key of ['analysis_metadata', 'quality', 'captured_at', 'capture_timezone', 'latitude', 'longitude', 'location_name', 'final_version_id']) delete photo[key];
        }
        store.put(state, 'current');
      };
      tx.oncomplete = () => { db.close(); resolve(summary); };
      tx.onerror = () => { db.close(); reject(tx.error); };
    };
  }));
  await page.reload();
  await expect(page.locator('.photo-card')).toHaveCount(12);
  await page.getByLabel('체험 인물').selectOption('jisu');
  await expect.poll(() => page.evaluate(({photoId, count}) => new Promise<boolean>((resolve, reject) => {
    const opening = indexedDB.open('zzik-browser-demo-v1', 1);
    opening.onerror = () => reject(opening.error);
    opening.onsuccess = () => {
      const db = opening.result;
      const request = db.transaction('state').objectStore('state').get('current');
      request.onsuccess = () => {
        const state = request.result, photo = state.photos.find((item: {id: string}) => item.id === photoId);
        db.close();
        resolve(state.photos.length === count && photo.captured_at === null && photo.final_version_id === null
          && Boolean(state.albums[0].owner_id) && state.albums[0].people[0].proposed_user_id === null);
      };
      request.onerror = () => { db.close(); reject(request.error); };
    };
  }), before)).toBe(true);
});
