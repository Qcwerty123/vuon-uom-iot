// Quản lý thiết bị (ADMIN) — đặc tả §16.1, UC11–UC13: đăng ký, cấp phát (secret một lần), cấp lại khóa,
// gán quyền, tạm khóa/mở khóa, thu hồi (nhập lại mã thiết bị).
import { useEffect, useState } from 'react'
import { del, get, patch, post } from '../api/client.js'
import { useDevices } from '../devices.jsx'
import {
  Card, CopyButton, Empty, ErrorBox, Modal, OnlineBadge, ReasonDialog, Spinner, StatusBadge, useTick, useToast,
} from '../components/ui.jsx'
import { DEVICE_STATUS, DEVICE_TYPE, PERMISSION, ROLE, fmtAgo } from '../labels.js'

const CAN_SUSPEND = new Set(['ACTIVE', 'OFFLINE', 'FAULT', 'MAINTENANCE'])
const CAN_DECOMMISSION = new Set(['ACTIVE', 'OFFLINE', 'FAULT', 'MAINTENANCE', 'SUSPENDED'])

export default function AdminDevices({ query }) {
  const { devices, loaded, error, reload, upsert } = useDevices()
  const toast = useToast()
  const [dialog, setDialog] = useState(null) // {kind, device}
  const [secret, setSecret] = useState(null) // kết quả provision / rotate
  const [showGone, setShowGone] = useState(false)
  const focus = Number(query.focus) || null
  useTick(5000)

  useEffect(() => { reload() }, [reload])

  const list = devices.filter((d) => showGone || d.status !== 'DECOMMISSIONED')
  const close = () => setDialog(null)

  const doProvision = async (d) => {
    try {
      const r = await post(`/devices/${d.id}/provision`)
      setSecret({ ...r, device: d, rotated: false })
      upsert({ id: d.id, status: 'PROVISIONED' })
    } catch (e) { toast(e.message, 'bad') }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Quản lý thiết bị</h1>
        <div className="row gap-s">
          <label className="check small"><input type="checkbox" checked={showGone} onChange={(e) => setShowGone(e.target.checked)} />Hiện thiết bị đã thu hồi</label>
          <button className="btn primary" onClick={() => setDialog({ kind: 'create' })}>+ Đăng ký thiết bị</button>
        </div>
      </div>
      <ErrorBox error={error} />
      <Card>
        {!loaded ? <Spinner /> : list.length === 0 ? <Empty>Chưa có thiết bị.</Empty> : (
          <div className="table-wrap">
            <table className="devices-table">
              <thead>
                <tr><th>Mã</th><th>Tên</th><th>Loại</th><th>Trạng thái</th><th>Kết nối</th><th>Lần cuối</th><th>Thao tác</th></tr>
              </thead>
              <tbody>
                {list.map((d) => (
                  <tr key={d.id} className={focus === d.id ? 'focus' : ''}>
                    <td className="mono"><a href={`#/devices/${d.id}`}>{d.deviceCode}</a></td>
                    <td>{d.name}</td>
                    <td>{DEVICE_TYPE[d.type]}</td>
                    <td><StatusBadge map={DEVICE_STATUS} value={d.status} /></td>
                    <td><OnlineBadge online={d.online} /></td>
                    <td className="small">{fmtAgo(d.lastSeenAt)}</td>
                    <td>
                      <div className="row wrap gap-s actions">
                        {d.status === 'REGISTERED' && (
                          <button className="btn small primary" onClick={() => setDialog({ kind: 'provision', device: d })}>Cấp phát</button>
                        )}
                        {!['REGISTERED', 'DECOMMISSIONED'].includes(d.status) && (
                          <button className="btn small" onClick={() => setDialog({ kind: 'rotate', device: d })}>Cấp lại khóa</button>
                        )}
                        {d.status !== 'DECOMMISSIONED' && (
                          <>
                            <button className="btn small" onClick={() => setDialog({ kind: 'assign', device: d })}>Gán quyền</button>
                            <button className="btn small" onClick={() => setDialog({ kind: 'edit', device: d })}>Sửa</button>
                          </>
                        )}
                        {CAN_SUSPEND.has(d.status) && (
                          <button className="btn small warn" onClick={() => setDialog({ kind: 'suspend', device: d })}>Tạm khóa</button>
                        )}
                        {d.status === 'SUSPENDED' && (
                          <button className="btn small" onClick={() => setDialog({ kind: 'resume', device: d })}>Mở khóa</button>
                        )}
                        {CAN_DECOMMISSION.has(d.status) && (
                          <button className="btn small danger" onClick={() => setDialog({ kind: 'decommission', device: d })}>Thu hồi</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {dialog?.kind === 'create' && <CreateDevice onClose={close} onDone={(d) => { upsert(d); reload(); toast(`Đã đăng ký ${d.deviceCode}`, 'ok') }} />}
      {dialog?.kind === 'edit' && <EditDevice device={dialog.device} onClose={close} onDone={(d) => { upsert(d); toast('Đã lưu', 'ok') }} />}
      {dialog?.kind === 'provision' && (
        <ReasonDialog title={`Cấp phát ${dialog.device.deviceCode}`} needReason={false} confirmText="Cấp phát"
          extra={<p>Hệ thống sẽ tạo tài khoản trên broker và sinh khóa bí mật. <b>Khóa chỉ hiển thị một lần</b>, hãy chép ngay vào <code>secrets.h</code>.</p>}
          onClose={close} onSubmit={() => doProvision(dialog.device)} />
      )}
      {dialog?.kind === 'rotate' && (
        <ReasonDialog title={`Cấp lại khóa ${dialog.device.deviceCode}`} needReason={false} confirmText="Cấp lại khóa" danger
          extra={<p>Khóa cũ hết hiệu lực ngay. Thiết bị sẽ không kết nối được cho tới khi nạp khóa mới.</p>}
          onClose={close}
          onSubmit={async () => {
            const r = await post(`/devices/${dialog.device.id}/rotate-secret`)
            setSecret({ ...r, device: dialog.device, rotated: true })
          }} />
      )}
      {dialog?.kind === 'suspend' && (
        <ReasonDialog title={`Tạm khóa ${dialog.device.deviceCode}`} confirmText="Tạm khóa" danger onClose={close}
          extra={<p>Broker từ chối kết nối của thiết bị và ngắt phiên đang mở.</p>}
          onSubmit={async (reason) => { upsert(await post(`/devices/${dialog.device.id}/suspend`, { reason })); toast('Đã tạm khóa', 'ok') }} />
      )}
      {dialog?.kind === 'resume' && (
        <ReasonDialog title={`Mở khóa ${dialog.device.deviceCode}`} confirmText="Mở khóa" onClose={close}
          extra={<p>Thiết bị chuyển về “Đã cấp phát, chờ kết nối” và hoạt động lại khi kết nối.</p>}
          onSubmit={async (reason) => { upsert(await post(`/devices/${dialog.device.id}/resume`, { reason })); toast('Đã mở khóa', 'ok') }} />
      )}
      {dialog?.kind === 'decommission' && <Decommission device={dialog.device} onClose={close} onDone={(d) => { upsert(d); toast('Đã thu hồi thiết bị', 'ok') }} />}
      {dialog?.kind === 'assign' && <Assignments device={dialog.device} onClose={close} />}
      {secret && <SecretDialog s={secret} onClose={() => setSecret(null)} />}
    </div>
  )
}

function CreateDevice({ onClose, onDone }) {
  const [form, setForm] = useState({ type: 'CONTROLLER', name: '', hwVersion: '', zoneId: '' })
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const submit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { setErr('Nhập tên thiết bị'); return }
    setBusy(true); setErr(null)
    try {
      const body = { type: form.type, name: form.name.trim() }
      if (form.hwVersion.trim()) body.hwVersion = form.hwVersion.trim()
      if (form.zoneId) body.zoneId = Number(form.zoneId)
      onDone(await post('/devices', body))
      onClose()
    } catch (ex) { setErr(ex) } finally { setBusy(false) }
  }
  return (
    <Modal title="Đăng ký thiết bị mới" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label>Loại
          <select value={form.type} onChange={set('type')}>
            <option value="CONTROLLER">Node điều khiển (ctl-xxxx)</option>
            <option value="CAMERA">Camera ESP32-CAM (cam-xxxx)</option>
          </select>
        </label>
        <label>Tên<input autoFocus maxLength={120} value={form.name} onChange={set('name')} placeholder="Ví dụ: Khay ươm A1" /></label>
        <label>Phiên bản phần cứng (không bắt buộc)<input maxLength={30} value={form.hwVersion} onChange={set('hwVersion')} placeholder="node1-r1" /></label>
        <label>Mã khu vực (không bắt buộc)<input type="number" min="1" value={form.zoneId} onChange={set('zoneId')} /></label>
        <p className="muted small">Mã thiết bị do hệ thống tự cấp. Sau khi đăng ký, bấm “Cấp phát” để lấy khóa nạp vào firmware.</p>
        <ErrorBox error={err} />
        <div className="row end gap-s">
          <button type="button" className="btn" onClick={onClose}>Hủy</button>
          <button className="btn primary" disabled={busy}>Đăng ký</button>
        </div>
      </form>
    </Modal>
  )
}

function EditDevice({ device, onClose, onDone }) {
  const [name, setName] = useState(device.name)
  const [note, setNote] = useState(device.note || '')
  const [err, setErr] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    try { onDone(await patch(`/devices/${device.id}`, { name: name.trim(), note })); onClose() } catch (ex) { setErr(ex) }
  }
  return (
    <Modal title={`Sửa ${device.deviceCode}`} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label>Tên<input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} /></label>
        <label>Ghi chú<textarea rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <ErrorBox error={err} />
        <div className="row end gap-s">
          <button type="button" className="btn" onClick={onClose}>Hủy</button>
          <button className="btn primary">Lưu</button>
        </div>
      </form>
    </Modal>
  )
}

function Decommission({ device, onClose, onDone }) {
  const [confirm, setConfirm] = useState('')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState(null)
  const ok = confirm === device.deviceCode && reason.trim()
  const submit = async (e) => {
    e.preventDefault()
    try {
      onDone(await post(`/devices/${device.id}/decommission`, { reason: reason.trim(), confirm }))
      onClose()
    } catch (ex) { setErr(ex) }
  }
  return (
    <Modal title={`Thu hồi ${device.deviceCode}`} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <div className="alert-box error">Thu hồi là vĩnh viễn: tài khoản broker bị xóa, thiết bị không thể kết nối lại.</div>
        <label>Lý do<input autoFocus value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} /></label>
        <label>Nhập lại mã <b className="mono">{device.deviceCode}</b> để xác nhận
          <input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
        </label>
        <ErrorBox error={err} />
        <div className="row end gap-s">
          <button type="button" className="btn" onClick={onClose}>Hủy</button>
          <button className="btn danger" disabled={!ok}>Thu hồi vĩnh viễn</button>
        </div>
      </form>
    </Modal>
  )
}

/** Hộp thoại hiển thị secret MỘT LẦN + khối secrets.h mẫu. */
function SecretDialog({ s, onClose }) {
  const [ack, setAck] = useState(false)
  const header = [
    '// secrets.h — KHÔNG commit file này',
    '#define WIFI_SSID      "ten-wifi-2.4GHz"',
    '#define WIFI_PASS      "mat-khau-wifi"',
    `#define MQTT_HOST      "${s.mqttHost}"`,
    `#define MQTT_PORT      ${s.mqttPort}`,
    `#define GARDEN_CODE    "${s.gardenCode}"`,
    `#define DEVICE_CODE    "${s.deviceCode}"`,
    `#define DEVICE_SECRET  "${s.secret}"`,
    ...(s.deviceCode.startsWith('cam-') ? [`#define UPLOAD_URL     "${s.uploadUrl}"`] : []),
    '#define NTP_SERVER     "pool.ntp.org"',
  ].join('\n')
  const tryClose = () => {
    if (ack || window.confirm('Khóa sẽ không hiển thị lại. Bạn đã chép khóa chưa?')) onClose()
  }
  return (
    <Modal title={s.rotated ? `Khóa mới của ${s.deviceCode}` : `Đã cấp phát ${s.deviceCode}`} onClose={tryClose} wide>
      <div className="stack">
        <div className="alert-box warn"><b>Khóa bí mật chỉ hiển thị một lần.</b> Đóng hộp thoại này là không xem lại được; nếu mất phải cấp lại khóa.</div>
        <div>
          <div className="label">Khóa bí mật (DEVICE_SECRET)</div>
          <div className="secret-row">
            <code className="secret">{s.secret}</code>
            <CopyButton text={s.secret} label="Sao chép khóa" />
          </div>
        </div>
        <dl className="kv">
          <dt>Mã thiết bị</dt><dd className="mono">{s.deviceCode}</dd>
          <dt>Mã vườn</dt><dd className="mono">{s.gardenCode}</dd>
          <dt>Broker MQTT</dt><dd className="mono">{s.mqttHost}:{s.mqttPort}</dd>
          {s.deviceCode.startsWith('cam-') && <><dt>Địa chỉ gửi ảnh</dt><dd className="mono">{s.uploadUrl}</dd></>}
        </dl>
        <div>
          <div className="row between">
            <div className="label">Khối <code>secrets.h</code> mẫu (điền WiFi rồi nạp firmware)</div>
            <CopyButton text={header} label="Sao chép secrets.h" />
          </div>
          <pre className="code">{header}</pre>
        </div>
        <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />Tôi đã chép khóa vào nơi an toàn</label>
        <div className="row end"><button className="btn primary" disabled={!ack} onClick={onClose}>Xong</button></div>
      </div>
    </Modal>
  )
}

function Assignments({ device, onClose }) {
  const toast = useToast()
  const [list, setList] = useState(null)
  const [users, setUsers] = useState([])
  const [userId, setUserId] = useState('')
  const [perm, setPerm] = useState('VIEW')
  const [err, setErr] = useState(null)
  const load = async () => {
    try {
      const [a, u] = await Promise.all([get(`/devices/${device.id}/assignments`), get('/users')])
      setList(a)
      setUsers(u.filter((x) => x.role !== 'ADMIN'))
    } catch (e) { setErr(e) }
  }
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const selected = users.find((u) => u.id === Number(userId))
  const add = async (e) => {
    e.preventDefault()
    if (!userId) return
    try {
      await post(`/devices/${device.id}/assignments`, { userId: Number(userId), permission: selected?.role === 'VIEWER' ? 'VIEW' : perm })
      toast('Đã gán quyền', 'ok')
      setUserId('')
      load()
    } catch (ex) { setErr(ex) }
  }
  const remove = async (a) => {
    if (!window.confirm(`Bỏ gán ${a.username}?`)) return
    try { await del(`/devices/${device.id}/assignments/${a.userId}`); load() } catch (ex) { setErr(ex) }
  }
  return (
    <Modal title={`Gán quyền ${device.deviceCode}`} onClose={onClose} wide>
      <div className="stack">
        <p className="muted small">Quản trị viên luôn có toàn quyền. Người xem (VIEWER) chỉ được quyền xem kể cả khi chọn “Điều khiển”.</p>
        <ErrorBox error={err} onClose={() => setErr(null)} />
        {!list ? <Spinner /> : list.length === 0 ? <Empty>Chưa gán cho ai.</Empty> : (
          <table>
            <thead><tr><th>Người dùng</th><th>Vai trò</th><th>Quyền</th><th /></tr></thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.userId}>
                  <td>{a.username}</td><td>{ROLE[a.role]}</td><td>{PERMISSION[a.permission]}</td>
                  <td><button className="btn small danger" onClick={() => remove(a)}>Bỏ gán</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form className="row wrap gap-s end-align" onSubmit={add}>
          <label className="inline">Người dùng
            <select value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">— chọn —</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.username} ({ROLE[u.role]})</option>)}
            </select>
          </label>
          <label className="inline">Quyền
            <select value={selected?.role === 'VIEWER' ? 'VIEW' : perm} disabled={selected?.role === 'VIEWER'} onChange={(e) => setPerm(e.target.value)}>
              <option value="VIEW">Chỉ xem</option>
              <option value="CONTROL">Điều khiển</option>
            </select>
          </label>
          <button className="btn primary" disabled={!userId}>Gán / cập nhật</button>
        </form>
      </div>
    </Modal>
  )
}
