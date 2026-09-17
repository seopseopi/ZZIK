import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { api, login, noHorizontalOverflow } from './helpers';

test('album settings, analysis recovery, photo deletion and member exit stay consistent', async ({ page, context, browser }, testInfo) => {
  test.setTimeout(150_000);
  page.setDefaultTimeout(15_000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const memberContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL as string, viewport: { width: 1440, height: 1000 } });
  const memberPage = await memberContext.newPage();
  memberPage.setDefaultTimeout(15_000);
  let albumId = '';
  try {
    await login(page);
    await login(memberPage, 'minji@moacut.local');
    const initialName = `설정 검증 ${Date.now()}`;
    const created = await (await api(context, '/albums', 'POST', { name: initialName })).json();
    albumId = created.id;
    await api(memberContext, '/albums/join', 'POST', { code: created.invite_code });
    await page.reload();
    await page.getByRole('button', { name: `${initialName} 사진 0장`, exact: true }).click();
    await page.getByRole('button', { name: '앨범 설정', exact: true }).click();
    let settings = page.getByRole('dialog', { name: '앨범 설정', exact: true });
    const renamed = `${initialName} 수정`;
    await settings.getByLabel('앨범 이름', { exact: true }).fill(renamed);
    await settings.getByLabel('앨범 소개', { exact: true }).fill('수정된 앨범 소개를 DB에 저장합니다.');
    await settings.getByRole('combobox', { name: '여행 시간대', exact: true }).selectOption('Asia/Tokyo');
    await settings.getByRole('button', { name: '앨범 정보 저장' }).click();
    await expect(settings).toContainText('앨범 정보를 저장했어요.');
    await expect(page.locator('.album-header h1')).toContainText(renamed);
    await expect(settings.getByRole('button', { name: '앨범 정보 저장' })).toBeDisabled();
    await settings.getByRole('button', { name: '새 초대코드 만들기' }).click();
    await expect(settings).toContainText('이미 참여한 멤버는 유지돼요.');
    await settings.getByRole('button', { name: '초대코드 변경', exact: true }).click();
    await expect(settings).toContainText('새 초대코드를 만들었어요.');
    const updated = await (await api(context, `/albums/${albumId}`)).json();
    expect(updated.invite_code).not.toBe(created.invite_code);
    expect(updated.timezone).toBe('Asia/Tokyo');
    await noHorizontalOverflow(page);
    await page.screenshot({ path: testInfo.outputPath('album-settings.png') });
    await testInfo.attach('Album management', { path: testInfo.outputPath('album-settings.png'), contentType: 'image/png' });
    await settings.getByRole('button', { name: '닫기', exact: true }).click();

    await memberPage.reload();
    await memberPage.getByRole('button', { name: `${renamed} 사진 0장`, exact: true }).click();
    await memberPage.getByRole('button', { name: '앨범 설정', exact: true }).click();
    const memberSettings = memberPage.getByRole('dialog', { name: '앨범 설정', exact: true });
    await expect(memberSettings.getByLabel('앨범 이름', { exact: true })).toBeDisabled();
    await expect(memberSettings.getByRole('button', { name: '새 초대코드 만들기' })).toHaveCount(0);
    await memberSettings.getByRole('button', { name: '닫기', exact: true }).click();

    const original = await readFile(path.resolve('public/demo/sample-no-face.jpg'));
    const session = await (await context.request.get('/api/auth/me')).json();
    const upload = await context.request.post(`/api/albums/${albumId}/photos`, {
      headers: { 'X-CSRF-Token': session.csrf_token },
      multipart: { file: { name: '관리검증.jpg', mimeType: 'image/jpeg', buffer: Buffer.concat([original, Buffer.from('outside-fixture')]) }, request_id: 'management-retry-photo' },
    });
    expect(upload.ok()).toBeTruthy();
    const photo = await upload.json();
    await expect.poll(async () => (await (await api(context, `/photos/${photo.id}`)).json()).analysis_status).toBe('failed');
    await page.reload();
    await page.getByRole('button', { name: '사진 정리 현황', exact: true }).click();
    const analysis = page.getByRole('dialog', { name: '사진 정리 현황', exact: true });
    await expect(analysis).toContainText('샘플 사진 분석 모드');
    await expect(analysis).toContainText('총 1장의 원본이 저장되어 있어요.');
    await expect(analysis).toContainText('관리검증.jpg');
    await analysis.getByRole('button', { name: '실패한 사진 재분석' }).click();
    await expect(analysis).toContainText('샘플에 없는 사진은 다시 요청해도 자동으로 분류되지 않아요.');
    const requeue = page.waitForResponse(response => response.url().endsWith('/reanalyze-failed') && response.request().method() === 'POST');
    await analysis.getByRole('button', { name: '재분석 요청', exact: true }).click();
    expect((await (await requeue).json()).queued).toBe(1);
    await expect(analysis).toContainText('1장의 분석을 다시 요청했어요.');
    await expect.poll(async () => (await (await api(context, `/photos/${photo.id}`)).json()).analysis_status).toBe('failed');
    await analysis.getByRole('button', { name: '닫기', exact: true }).click();
    await page.getByRole('checkbox', { name: '관리검증.jpg 선택', exact: true }).check();
    await expect(page.locator('.selection-bar')).toBeVisible();
    await page.getByRole('button', { name: '관리검증.jpg 보정하기', exact: true }).click();
    const editor = page.getByRole('dialog', { name: '사진 보정 및 함께 고르기' });
    await editor.getByRole('navigation', { name: '사진 상세 메뉴' }).getByRole('button', { name: '사진 정보', exact: true }).click();
    await editor.getByRole('button', { name: '사진 삭제', exact: true }).click();
    await expect(editor.getByRole('button', { name: '사진 영구 삭제', exact: true })).toBeDisabled();
    await editor.getByRole('checkbox', { name: '모든 멤버에게서 삭제되며 되돌릴 수 없다는 점을 확인했어요.' }).check();
    await editor.getByRole('button', { name: '사진 영구 삭제', exact: true }).click();
    await expect(editor).not.toBeVisible();
    await expect(page.locator('.photo-card')).toHaveCount(0);
    await expect(page.locator('.selection-bar')).toHaveCount(0);
    const photoResponse = await context.request.get(`/api/photos/${photo.id}`);
    expect(photoResponse.status()).toBe(404);

    await page.getByRole('button', { name: '앨범 설정', exact: true }).click();
    settings = page.getByRole('dialog', { name: '앨범 설정', exact: true });
    await settings.getByRole('button', { name: '민지 앨범에서 내보내기', exact: true }).click();
    await settings.getByRole('button', { name: '멤버 내보내기', exact: true }).click();
    await expect(settings).toContainText('민지님을 앨범에서 내보냈어요.');
    expect((await memberContext.request.get(`/api/albums/${albumId}`)).status()).toBe(404);
    await api(memberContext, '/albums/join', 'POST', { code: updated.invite_code });
    await memberPage.reload();
    await memberPage.getByRole('button', { name: `${renamed} 사진 0장`, exact: true }).click();
    await memberPage.getByRole('button', { name: '앨범 설정', exact: true }).click();
    await memberSettings.getByRole('button', { name: '이 앨범 나가기', exact: true }).click();
    await memberSettings.getByRole('button', { name: '앨범에서 나가기', exact: true }).click();
    await expect(memberSettings).not.toBeVisible();
    await expect(memberPage.locator('.album-cards')).toBeVisible();
    expect((await memberContext.request.get(`/api/albums/${albumId}`)).status()).toBe(404);

    await settings.getByRole('button', { name: '앨범 삭제하기' }).click();
    await expect(settings.getByRole('button', { name: '영구 삭제', exact: true })).toBeDisabled();
    await settings.getByLabel('삭제할 앨범 이름').fill(renamed);
    await settings.getByRole('button', { name: '영구 삭제', exact: true }).click();
    await expect(settings).not.toBeVisible();
    await expect(page.locator('.album-cards')).toBeVisible();
    expect((await context.request.get(`/api/albums/${albumId}`)).status()).toBe(404);
    albumId = '';
    await page.reload();
    await expect(page.locator('.album-header h1')).not.toContainText(renamed);
    expect(errors).toEqual([]);
  } finally {
    if (albumId) await api(context, `/albums/${albumId}`, 'DELETE');
    await memberContext.close();
  }
});
