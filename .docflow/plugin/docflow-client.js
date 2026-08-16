return {
  inject: ['timer'],
  async apply(ctx) {
    const slots = ctx.get('slots')
    if (slots === undefined) return

    styles.insert('.dwf{font-family:ui-sans-serif,system-ui,-apple-system,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;border:1px solid rgba(127,127,127,.28);border-radius:12px;padding:12px 14px;background:rgba(127,127,127,.05)}' +
      '.dwf h3{margin:0 0 2px;font-size:15px;font-weight:700}.dwf .dwf-sub{margin:0 0 10px;font-size:12px;color:#8a8a8a}' +
      '.dwf .dwf-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:6px 0}' +
      '.dwf label.dwf-up{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:8px;background:#1F6FB2;color:#fff;font-size:13px;cursor:pointer;user-select:none}' +
      '.dwf label.dwf-up:active{opacity:.85}' +
      '.dwf .dwf-btn{display:inline-block;padding:4px 10px;border-radius:6px;border:1px solid rgba(127,127,127,.4);background:transparent;color:inherit;font-size:12px;cursor:pointer;text-decoration:none}' +
      '.dwf .dwf-btn:hover{background:rgba(127,127,127,.14)}' +
      '.dwf .dwf-dl{border-color:#2E8B57;color:#2E8B57;font-weight:600}' +
      '.dwf .dwf-sec{margin-top:10px;font-size:12.5px;font-weight:600;color:#5a5a5a}' +
      '.dwf ul.dwf-list{list-style:none;margin:4px 0 0;padding:0}' +
      '.dwf ul.dwf-list li{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:8px;font-size:12.5px}' +
      '.dwf ul.dwf-list li:nth-child(odd){background:rgba(127,127,127,.08)}' +
      '.dwf .dwf-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.dwf .dwf-badge{flex:none;font-size:10.5px;padding:1px 7px;border-radius:999px;background:rgba(31,111,178,.14);color:#1F6FB2;font-weight:600}' +
      '.dwf .dwf-size{flex:none;color:#999;font-size:11px}' +
      '.dwf .dwf-prev{margin-top:8px;border-radius:8px;background:rgba(127,127,127,.09);padding:8px 10px;font-size:12px;white-space:pre-wrap;max-height:220px;overflow:auto;color:#777}' +
      '.dwf .dwf-msg{margin-top:8px;font-size:12px;color:#C0392B}.dwf .dwf-ok{color:#2E8B57}' +
      '.dwf .dwf-empty{font-size:12px;color:#999;padding:4px 2px}' +
      '.dwf-up2{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:8px;background:rgba(31,111,178,.12);color:#1F6FB2;font-size:12.5px;cursor:pointer;user-select:none;border:1px solid rgba(31,111,178,.25);white-space:nowrap}' +
      '.dwf-up2:hover{background:rgba(31,111,178,.22)}.dwf-up2:active{opacity:.8}' +
      '.dwf-up2.busy{opacity:.6;cursor:progress}' +
      '.dwf-dropover{position:fixed;left:50%;transform:translateX(-50%);bottom:110px;z-index:9999;display:flex;align-items:center;gap:10px;padding:12px 22px;border:2px dashed #1F6FB2;border-radius:14px;background:rgba(31,111,178,.12);color:#1F6FB2;font-size:14px;font-weight:600;box-shadow:0 8px 30px rgba(0,0,0,.18);pointer-events:auto;user-select:none;backdrop-filter:blur(4px)}' +
      '.dwf-dropover.busy{opacity:.7}' +
      '.dwf-dropover .spin{display:inline-block;animation:dwf-spin 1s linear infinite}.dwf-dropover.hidden{display:none}' +
      '@keyframes dwf-spin{to{transform:rotate(360deg)}}' +
      '.dwf-dock{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px;color:#777;padding:2px 2px}' +
      '.dwf-dock-title{font-weight:700;color:#1F6FB2;font-size:12.5px}' +
      '.dwf-dock-meta{color:#999;white-space:nowrap}' +
      '.dwf-dock-file{display:inline-block;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#2E8B57;text-decoration:none;font-weight:600}' +
      '.dwf-dock-file:hover{text-decoration:underline}' +
      '.dwf-dock .dwf-btn{font-size:11px;padding:2px 8px}' +
      '.dwf-tblwrap{margin-top:6px;border:1px solid rgba(127,127,127,.25);border-radius:10px;overflow:hidden}' +
      '.dwf-tbl{width:100%;border-collapse:collapse;font-size:12px;display:block;max-height:280px;overflow:auto}' +
      '.dwf-tbl thead,.dwf-tbl tbody{display:table;width:100%;table-layout:fixed}' +
      '.dwf-tbl th{position:sticky;top:0;background:#1F6FB2;color:#fff;font-weight:600;text-align:left;padding:6px 10px;font-size:12px;z-index:1}' +
      '.dwf-tbl td{padding:5px 10px;border-top:1px solid rgba(127,127,127,.12);vertical-align:middle;word-break:break-all}' +
      '.dwf-tbl tbody tr:nth-child(odd) td{background:rgba(127,127,127,.05)}' +
      '.dwf-tbl tbody tr:hover td{background:rgba(31,111,178,.08)}' +
      '.dwf-tbl th:nth-child(1),.dwf-tbl td:nth-child(1){width:32%}' +
      '.dwf-tbl th:nth-child(2),.dwf-tbl td:nth-child(2){width:10%}' +
      '.dwf-tbl th:nth-child(3),.dwf-tbl td:nth-child(3){width:15%}' +
      '.dwf-tbl th:nth-child(4),.dwf-tbl td:nth-child(4){width:22%}' +
      '.dwf-tbl th:nth-child(5),.dwf-tbl td:nth-child(5){width:21%}' +
      '.dwf-tbl-name a{color:#1F6FB2;text-decoration:none;font-weight:600}' +
      '.dwf-tbl-name a:hover{text-decoration:underline}' +
      '.dwf-dir{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}' +
      '.dwf-dir-in{background:rgba(46,139,87,.14);color:#2E8B57}' +
      '.dwf-dir-out{background:rgba(31,111,178,.14);color:#1F6FB2}' +
      '.dwf-tbl-time{color:#999;white-space:nowrap}' +
      '.dwf-tbl-req{color:#555}.dwf-tbl-sum{color:#777}')

    // ---------- 共享上传逻辑 ----------
    async function toB64(file) {
      const buf = await file.arrayBuffer()
      const bytes = new Uint8Array(buf)
      let bin = ''
      const CHUNK = 0x8000
      for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK))
      }
      return btoa(bin)
    }

    // 返回 {done: string[], failed: string}
    async function uploadFiles(fileList, inputActions) {
      const list = Array.from(fileList || [])
      const names = list.map((f) => f.name)
      const ia = inputActions
      // 拖入后立即在输入框显示文件名，让用户知道已接住
      if (ia && typeof ia.setDraft === 'function') {
        try {
          ia.setDraft('📎 ' + names.join('、'))
        } catch (e) {}
      }
      const done = []
      let failed = ''
      for (const f of list) {
        if (f.size > 90 * 1024 * 1024) {
          failed += f.name + ' 超限; '
          continue
        }
        try {
          const b64 = await toB64(f)
          const r = await host.call('upload', { name: f.name, dataB64: b64 })
          if (r && r.ok) {
            done.push(r.file.name + (r.chars ? '（' + r.chars + '字）' : ''))
          } else {
            failed += f.name + ': ' + ((r && r.error) || '失败') + '; '
          }
        } catch (e) {
          failed += f.name + ': ' + String((e && e.message) || e) + '; '
        }
      }
      if (done.length) {
        if (ia && typeof ia.setDraft === 'function') {
          try {
            ia.setDraft('已上传：' + done.join('、') + '。请告诉我你想如何创建或修改这些文档。')
          } catch (e) {}
        }
      } else if (failed && ia && typeof ia.setDraft === 'function') {
        try {
          ia.setDraft('上传失败：' + failed.slice(0, 100))
        } catch (e) {}
      }
      return { done: done, failed: failed }
    }

    // 判断一次拖拽中是否包含文档文件（非图片）。纯图片拖入返回 false → 完全放行给原生图片附件。
    function dragHasDoc(e) {
      try {
        const dt = e && e.dataTransfer
        if (!dt) return false
        if (dt.items && dt.items.length) {
          let anyFile = false
          for (let i = 0; i < dt.items.length; i++) {
            const item = dt.items[i]
            if (item.kind !== 'file') continue
            anyFile = true
            const type = (item.type || '').toLowerCase()
            if (type && !type.startsWith('image/')) return true
          }
          return false // 全是图片（或无文件项）
        }
        if (dt.files && dt.files.length) {
          for (let i = 0; i < dt.files.length; i++) {
            const type = (dt.files[i].type || '').toLowerCase()
            if (type && !type.startsWith('image/')) return true
          }
          return false
        }
        return false
      } catch (e2) {
        return false
      }
    }

    // ---------- 输入区浮动拖放层：平时不可见，拖入文档时浮现 ----------
    let dragDepth = 0
    function DropOverlay(props) {
      const h = React.createElement
      const [show, setShow] = React.useState(false)
      const [busy, setBusy] = React.useState(false)
      const [note, setNote] = React.useState('')

      React.useEffect(() => {
        // 原生图片附件在 document 冒泡阶段监听 drag/drop（hasFiles 即 preventDefault、
        // 显示全屏提示层、drop 按图片摄入并报"仅支持 PNG/JPG/WebP/GIF"）。
        // 因此这里必须用捕获阶段（先执行）+ stopPropagation 阻断原生；纯图片放行。
        function onDragEnter(e) {
          if (!dragHasDoc(e)) return
          dragDepth++
          setShow(true)
          if (e.preventDefault) e.preventDefault()
          if (e.stopPropagation) e.stopPropagation()
        }
        function onDragOver(e) {
          if (!dragHasDoc(e)) return
          if (e.preventDefault) e.preventDefault()
          if (e.stopPropagation) e.stopPropagation()
          try { if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy' } catch (e2) {}
        }
        function onDragLeave(e) {
          if (!dragHasDoc(e)) return
          dragDepth = Math.max(0, dragDepth - 1)
          if (dragDepth === 0) setShow(false)
          if (e.preventDefault) e.preventDefault()
          if (e.stopPropagation) e.stopPropagation()
        }
        function onDrop(e) {
          if (!dragHasDoc(e)) return
          dragDepth = 0
          setShow(false)
          if (e.preventDefault) e.preventDefault()
          if (e.stopPropagation) e.stopPropagation()
          const files = e.dataTransfer && e.dataTransfer.files
          if (files && files.length) {
            setBusy(true)
            uploadFiles(files, props && props.inputActions).then((r) => {
              setBusy(false)
              if (r.done.length) setNote('✓ 已上传 ' + r.done.length + ' 个文件')
              if (r.failed) setNote('⚠ ' + r.failed.slice(0, 80))
            })
          }
        }
        document.addEventListener('dragenter', onDragEnter, true)
        document.addEventListener('dragover', onDragOver, true)
        document.addEventListener('dragleave', onDragLeave, true)
        document.addEventListener('drop', onDrop, true)
        return () => {
          document.removeEventListener('dragenter', onDragEnter, true)
          document.removeEventListener('dragover', onDragOver, true)
          document.removeEventListener('dragleave', onDragLeave, true)
          document.removeEventListener('drop', onDrop, true)
        }
      }, [])

      if (!show) return null
      return h('div', { className: 'dwf-dropover' + (busy ? ' busy' : '') },
        busy ? h('span', { className: 'spin' }, '⏳') : h('span', null, '📥'),
        busy ? '正在上传文档…' : '松开以上传文档（docx / pdf / ppt / txt；图片保持原附件方式）',
        note ? h('span', null, '　' + note) : null,
      )
    }

    slots.inject('conversation.input.overlay', () => slots.register(
      { name: 'conversation.input.overlay', id: 'docf-dropoverlay', order: 100 },
      (props) => React.createElement(DropOverlay, props),
    ))

    // ---------- 输入区左侧上传按钮（支持拖放） ----------
    function UploadEntry(props) {
      const h = React.createElement
      const [busy, setBusy] = React.useState(false)
      const [note, setNote] = React.useState('')
      const [over, setOver] = React.useState(false)

      async function onFiles(fileList) {
        if (!fileList || !fileList.length) return
        setBusy(true)
        setNote('')
        const r = await uploadFiles(fileList, props && props.inputActions)
        setBusy(false)
        if (r.done.length) setNote('✓ ' + r.done.length)
        if (r.failed) setNote('⚠ ' + r.failed.slice(0, 50))
      }

      return h('label', {
        className: 'dwf-up2' + (busy ? ' busy' : '') + (over ? ' over' : ''),
        title: '上传文档（txt/md/docx/pdf/ppt/pptx/xlsx，≤90MB），也可将文档文件直接拖入输入区',
        onDragOver: (e) => { e.preventDefault(); setOver(true) },
        onDragLeave: () => setOver(false),
        onDrop: (e) => {
          e.preventDefault()
          setOver(false)
          onFiles(e.dataTransfer && e.dataTransfer.files)
        },
      },
        busy ? '上传中…' : '📎 文档',
        note ? h('span', null, note) : null,
        h('input', {
          type: 'file',
          multiple: true,
          accept: '.txt,.md,.docx,.pdf,.ppt,.pptx,.xlsx',
          style: { display: 'none' },
          onChange: (e) => { onFiles(e.target.files); e.target.value = '' },
        }),
      )
    }

    slots.inject('conversation.input.left', () => slots.register(
      { name: 'conversation.input.left', id: 'docf-upload', order: 5 },
      (props) => React.createElement(UploadEntry, props),
    ))

    // ---------- run 卡片面板：文件列表 + 下载 ----------
    function DocPanel() {
      const h = React.createElement
      const [uploads, setUploads] = React.useState([])
      const [outputs, setOutputs] = React.useState([])
      const [msg, setMsg] = React.useState('')
      const [msgOk, setMsgOk] = React.useState(true)
      const [preview, setPreview] = React.useState(null)
      const [engineOk, setEngineOk] = React.useState(true)

      function kb(n) { return ((n || 0) / 1024).toFixed(1) + ' KB' }

      function refresh() {
        return host.call('list', { kind: 'all' }).then((r) => {
          if (r && r.ok) {
            setUploads((r.items || []).filter((i) => i.kind === 'uploads'))
            setOutputs((r.items || []).filter((i) => i.kind === 'outputs'))
          }
        }).catch((e) => {
          setMsg(String((e && e.message) || e))
          setMsgOk(false)
        })
      }

      function checkEngine() {
        return host.call('status', {}).then((s) => {
          if (s && s.ok) setEngineOk(!!s.engineReady)
        }).catch(() => {})
      }

      React.useEffect(() => {
        checkEngine()
        refresh()
        const stop = ctx.interval(() => { refresh() }, 8000)
        return stop
      }, [])

      async function onRemove(id) {
        try { await host.call('remove', { fileId: id }) } catch (e) {}
        await refresh()
      }

      async function togglePreview(id) {
        if (preview && preview.fileId === id) {
          setPreview(null)
          return
        }
        try {
          const r = await host.call('parse', { fileId: id, maxChars: 3000 })
          if (r && r.ok) setPreview({ fileId: id, text: r.text })
        } catch (e) {
          setMsg('预览失败: ' + String((e && e.message) || e))
          setMsgOk(false)
        }
      }

      const uploadRows = uploads.map((i) =>
        h('li', { key: i.fileId },
          h('span', { className: 'dwf-badge' }, String(i.format || 'file').toUpperCase()),
          h('span', { className: 'dwf-name', title: i.name }, i.name),
          h('span', { className: 'dwf-size' }, kb(i.size)),
          h('button', { className: 'dwf-btn', onClick: () => togglePreview(i.fileId) }, (preview && preview.fileId === i.fileId) ? '收起' : '预览'),
          h('button', { className: 'dwf-btn', onClick: () => onRemove(i.fileId) }, '删除'),
        ))
      const outputRows = outputs.map((i) =>
        h('li', { key: i.fileId },
          h('span', { className: 'dwf-badge' }, String(i.format || 'file').toUpperCase()),
          h('span', { className: 'dwf-name', title: i.name }, i.name),
          h('span', { className: 'dwf-size' }, kb(i.size)),
          h('a', { className: 'dwf-btn dwf-dl', href: i.downloadUrl, download: i.name }, '下载'),
        ))

      return h('div', { className: 'dwf' },
        h('h3', null, '📄 文档工作流'),
        h('p', { className: 'dwf-sub' }, engineOk
          ? '将 docx/pdf/ppt/txt 文件拖入输入区即可上传；生成结果在此下载'
          : '⚠ 文档引擎未就绪，请查看聊天反馈'),
        h('div', { className: 'dwf-row' },
          h('button', { className: 'dwf-btn', onClick: () => refresh() }, '刷新'),
        ),
        h('div', { className: 'dwf-sec' }, '已上传（' + uploads.length + '）'),
        uploads.length ? h('ul', { className: 'dwf-list' }, uploadRows) : h('div', { className: 'dwf-empty' }, '暂无上传文件'),
        preview ? h('pre', { className: 'dwf-prev' }, preview.text) : null,
        h('div', { className: 'dwf-sec' }, '生成结果（' + outputs.length + '）'),
        outputs.length ? h('ul', { className: 'dwf-list' }, outputRows) : h('div', { className: 'dwf-empty' }, '暂无生成文件'),
        msg ? h('div', { className: msgOk ? 'dwf-msg dwf-ok' : 'dwf-msg' }, msg) : null,
      )
    }

    slots.inject('tool.view.cordis', () => slots.register(
      { name: 'tool.view.cordis', key: 'self' },
      () => React.createElement(DocPanel),
    ))

    // ---------- 输入框下方常驻文档条（conversation.composer.dock，始终可见） ----------
    function DockStrip() {
      const h = React.createElement
      const [uploads, setUploads] = React.useState([])
      const [outputs, setOutputs] = React.useState([])
      const [expanded, setExpanded] = React.useState(false)
      const [msg, setMsg] = React.useState('')
      const [msgOk, setMsgOk] = React.useState(true)

      function refresh() {
        return host.call('list', { kind: 'all' }).then((r) => {
          if (r && r.ok) {
            setUploads((r.items || []).filter((i) => i.kind === 'uploads'))
            setOutputs((r.items || []).filter((i) => i.kind === 'outputs'))
          }
        }).catch((e) => {
          setMsg(String((e && e.message) || e))
          setMsgOk(false)
        })
      }

      React.useEffect(() => {
        refresh()
        const stop = ctx.interval(() => { refresh() }, 10000)
        return stop
      }, [])

      const recent = outputs.slice(0, 2).concat(uploads.slice(0, 1))
      const all = outputs.concat(uploads)
      return h('div', null,
        h('div', { className: 'dwf-dock' },
          h('span', { className: 'dwf-dock-title' }, '📄 文档工作流'),
          h('span', { className: 'dwf-dock-meta' },
            uploads.length + ' 上传 · ' + outputs.length + ' 生成'),
          recent.map((i) =>
            h('a', { key: i.fileId, className: 'dwf-dock-file', href: i.downloadUrl, download: i.name, title: i.name },
              '⬇ ' + i.name),
          ),
          h('button', { className: 'dwf-btn', onClick: () => setExpanded(!expanded) }, expanded ? '收起 ▲' : '展开 ▾'),
          h('button', { className: 'dwf-btn', onClick: () => refresh() }, '刷新'),
          msg ? h('span', { className: msgOk ? 'dwf-msg dwf-ok' : 'dwf-msg' }, msg) : null,
        ),
        expanded ? h('div', { className: 'dwf-tblwrap' },
          h('table', { className: 'dwf-tbl' },
            h('thead', null,
              h('tr', null,
                h('th', null, '文件名'),
                h('th', null, '方向'),
                h('th', null, '修改时间'),
                h('th', null, '用户要求'),
                h('th', null, '简要修改内容'),
              )),
            h('tbody', null,
              all.map((i) =>
                h('tr', { key: i.fileId },
                  h('td', { className: 'dwf-tbl-name' },
                    h('a', { href: i.downloadUrl, download: i.name, title: i.name }, i.name)),
                  h('td', null,
                    h('span', { className: i.kind === 'outputs' ? 'dwf-dir dwf-dir-out' : 'dwf-dir dwf-dir-in' },
                      i.kind === 'outputs' ? '⬇ 生成' : '⬆ 上传')),
                  h('td', { className: 'dwf-tbl-time' }, i.mtime || ''),
                  h('td', { className: 'dwf-tbl-req' }, i.request || '—'),
                  h('td', { className: 'dwf-tbl-sum' }, i.summary || '—'),
                )),
            )),
          all.length ? null : h('div', { className: 'dwf-empty' }, '暂无文件，拖入文档即可上传'),
        ) : null,
      )
    }

    slots.inject('conversation.composer.dock', () => slots.register(
      { name: 'conversation.composer.dock', id: 'docf-dock', order: 10 },
      () => React.createElement(DockStrip),
    ))
  },
}
