import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from '../api'
import authStorage from '../authStorage'

/**
 * BASE-SEC-43. Logging out used to clear localStorage and nothing else, so the
 * refresh token stayed valid on the server for its full 14 days. The revoke
 * endpoint already existed; it was simply never called. These tests hold the
 * call in place, and hold the local clear unconditional.
 *
 * Phase L3: the refresh token moved to an HttpOnly cookie the server manages
 * — the browser attaches it automatically (credentials: "include"), so it no
 * longer appears in the request body and authStorage no longer has a
 * refresh-token getter to assert against.
 */
describe('api.logout', () => {
  beforeEach(() => {
    authStorage.clearAll()
    vi.restoreAllMocks()
  })

  it('revokes the refresh token on the server, then clears local state', async () => {
    authStorage.setToken('access-abc')

    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal('fetch', fetchMock)

    await api.logout()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/auth\/logout$/)
    expect(opts.method).toBe('POST')
    expect(opts.credentials).toBe('include')
    expect(opts.body).toBeUndefined()
    expect(opts.headers.Authorization).toBe('Bearer access-abc')

    expect(authStorage.getToken()).toBeFalsy()
  })

  it('still clears local state when the revoke call fails', async () => {
    authStorage.setToken('access-abc')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    await api.logout()

    // Being offline must not leave the user logged in on this device — that is
    // the outcome they can actually see.
    expect(authStorage.getToken()).toBeFalsy()
  })

  it('still calls the endpoint when no access token is held', async () => {
    // This test previously asserted the OPPOSITE — that logout skipped the
    // call when there was no access token in memory. That was the bug: the
    // access token is memory-only now, so it is routinely absent at logout
    // (after any reload, or once it expires), and skipping the call meant
    // the refresh cookie was never revoked while the UI reported success.
    // On a shared machine the next person's boot refresh resumed the
    // previous session. The cookie is the real credential, so the call has
    // to go out regardless of what is in memory.
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal('fetch', fetchMock)

    await api.logout()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/auth\/logout$/)
    expect(opts.credentials).toBe('include')
    expect(opts.headers.Authorization).toBeUndefined()
  })

  it('sends the csrf header, since logout authenticates by cookie now', async () => {
    document.cookie = 'csrf_token=logout-csrf'
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal('fetch', fetchMock)

    authStorage.setToken('access-abc')
    await api.logout()

    expect(fetchMock.mock.calls[0][1].headers['X-CSRF-Token']).toBe('logout-csrf')
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  })
})
