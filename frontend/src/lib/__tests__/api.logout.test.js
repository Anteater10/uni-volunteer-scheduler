import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from '../api'
import authStorage from '../authStorage'

/**
 * BASE-SEC-43. Logging out used to clear localStorage and nothing else, so the
 * refresh token stayed valid on the server for its full 14 days. The revoke
 * endpoint already existed; it was simply never called. These tests hold the
 * call in place, and hold the local clear unconditional.
 */
describe('api.logout', () => {
  beforeEach(() => {
    authStorage.clearAll()
    vi.restoreAllMocks()
  })

  it('revokes the refresh token on the server, then clears local state', async () => {
    authStorage.setToken('access-abc')
    authStorage.setRefreshToken('refresh-xyz')

    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal('fetch', fetchMock)

    await api.logout()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/auth\/logout$/)
    expect(opts.method).toBe('POST')
    // The server revokes the token named in the body, so sending the wrong one
    // (or none) would look like a successful logout and revoke nothing.
    expect(JSON.parse(opts.body)).toEqual({ refresh_token: 'refresh-xyz' })
    expect(opts.headers.Authorization).toBe('Bearer access-abc')

    expect(authStorage.getToken()).toBeFalsy()
    expect(authStorage.getRefreshToken()).toBeFalsy()
  })

  it('still clears local state when the revoke call fails', async () => {
    authStorage.setToken('access-abc')
    authStorage.setRefreshToken('refresh-xyz')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    await api.logout()

    // Being offline must not leave the user logged in on this device — that is
    // the outcome they can actually see.
    expect(authStorage.getToken()).toBeFalsy()
    expect(authStorage.getRefreshToken()).toBeFalsy()
  })

  it('does not call the endpoint when there is nothing to revoke', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await api.logout()

    expect(fetchMock).not.toHaveBeenCalled()
  })
})
