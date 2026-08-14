return {
  inject: ['shell', 'fs', 'webServer'],
  apply(ctx) {
    const shell = ctx.shell
    const fs = ctx.fs
    const webServer = ctx.webServer
    const base = '/opt/oral-mucosa-agent'
    const ROOT = base + '/.docflow'
    const PY = ROOT + '/venv/bin/python'
    const ENGINE = ROOT + '/engine/docflow_engine.py'
    const UPLOADS = ROOT + '/uploads'
    const OUTPUTS = ROOT + '/outputs'
    const MAX_BYTES = 100 * 1024 * 1024
    const UPLOAD_MAX_B64 = 125 * 1024 * 1024

    const files = new Map()
    let seq = 0

    // fs/shell 的默认沙箱策略工作区根是 /root，本会话工作区在 /opt/oral-mucosa-agent，
    // 所有写操作必须显式声明 workspace-write + 工作区根
    const POLICY = { mode: 'workspace-write', workspaceRoot: base }

    function q(s) {
      return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\$/g, '\\$').replace(/`/g, '\\`') + '"'
    }
    function sanitize(name) {
      let s = String(name == null ? 'file' : name)
        .replace(/[\s\\\/:*?"<>|\x00-\x1f]/g, '_')
        .replace(/^\.+/, '')
        .replace(/_+/g, '_')
      if (s.length > 90) s = s.slice(0, 90)
      return s || 'file'
    }
    function extOf(name) {
      const m = /\.([A-Za-z0-9]+)$/.exec(String(name))
      return m ? m[1].toLowerCase() : ''
    }
    function fmtOf(name) {
      const e = extOf(name)
      if (e === 'markdown') return 'md'
      return ['docx', 'pptx', 'ppt', 'pdf', 'txt', 'md'].indexOf(e) >= 0 ? e : 'file'
    }
    function newId(kind) { return kind + '_' + Date.now().toString(36) + '_' + (seq++).toString(36) }
    // 下载地址用相对路径：浏览器会按当前页面 origin 解析，
    // 用户通过任意地址（127.0.0.1 / 服务器IP / 域名 / 端口转发）访问 GUI 均可下载
    function urlOf(id) { return '/dsh-docflow/download/' + id }
    function kb(n) { return ((n || 0) / 1024).toFixed(1) + ' KB' }
    function pct(s) {
      const bytes = new TextEncoder().encode(String(s))
      let out = ''
      for (let i = 0; i < bytes.length; i++) {
        const b = bytes[i]
        if ((b >= 0x41 && b <= 0x5A) || (b >= 0x61 && b <= 0x7A) || (b >= 0x30 && b <= 0x39) || b === 0x2D || b === 0x2E || b === 0x5F || b === 0x7E) out += String.fromCharCode(b)
        else out += '%' + (b < 16 ? '0' : '') + b.toString(16).toUpperCase()
      }
      return out
    }
    const MIME = {
      docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      ppt: 'application/vnd.ms-powerpoint',
      pdf: 'application/pdf',
      txt: 'text/plain; charset=utf-8',
      md: 'text/markdown; charset=utf-8',
    }

    function pick(info) {
      return {
        fileId: info.id,
        name: info.name,
        kind: info.kind,
        size: info.size || 0,
        format: info.format,
        createdAt: info.createdAt,
        downloadUrl: urlOf(info.id),
      }
    }

    async function runPy(args, stdin) {
      try {
        const spec = shell.resolve({
          command: PY + ' ' + ENGINE + ' ' + args,
          workdir: ROOT,
          timeoutMs: 240000,
          stdoutMaxBytes: 64 * 1024 * 1024,
          stdin: stdin,
          sandboxPolicy: POLICY,
        })
        const res = await shell.run(spec)
        return res
      } catch (e) {
        return { exitCode: -1, stdout: '', stderr: String((e && e.message) || e) }
      }
    }
    // 把 JSON 数据写入临时文件，返回其路径（绕开 stdin 传递的不确定性）
    async function writeJsonTemp(payload) {
      const tmpPath = ROOT + '/tmp/spec_' + newId('t') + '.json'
      await fs.writeText(await fs.resolve(tmpPath), typeof payload === 'string' ? payload : JSON.stringify(payload), undefined, undefined, POLICY)
      return tmpPath
    }
    // 带 spec 文件执行 create/edit：数据落盘后把路径作为最后一个参数
    async function runPySpec(sub, fmt, outPath, extraPath, payload) {
      const specPath = await writeJsonTemp(payload)
      let args = sub + ' ' + fmt + ' ' + q(outPath)
      if (extraPath) args += ' ' + q(extraPath)
      args += ' ' + q(specPath)
      return runPy(args)
    }
    // 把 JSON 数据写入临时文件，再执行一个引擎命令（参数以文件路径追加）
    async function runPyJson(sub, payload, extraArgs) {
      const jsonPath = await writeJsonTemp(payload)
      let args = sub + ' ' + q(jsonPath)
      if (extraArgs) args += ' ' + extraArgs
      return runPy(args)
    }
    function parseResult(res) {
      try { return JSON.parse(String((res && res.stdout) || '')) } catch (e) { return null }
    }

    // ---------- 文献检索 / 核查（真实来源：PubMed E-utilities + Crossref） ----------
    async function handleLitSearch(args) {
      const term = String(args.term || '').trim()
      if (!term) return { ok: false, error: '缺少检索词 term' }
      const retmax = Math.min(Math.max(parseInt(args.maxResults, 10) || 8, 1), 20)
      const res = await runPy('lit-search ' + q(term) + ' ' + retmax)
      const j = parseResult(res)
      if (!j || !j.ok) return { ok: false, error: '检索失败: ' + String(res.stderr || res.stdout || '').slice(0, 400) }
      return { ok: true, count: j.count, items: j.items || [] }
    }

    async function handleLitCrossref(args) {
      const query = String(args.query || '').trim()
      if (!query) return { ok: false, error: '缺少查询词 query' }
      const rows = Math.min(Math.max(parseInt(args.maxResults, 10) || 5, 1), 10)
      const res = await runPy('lit-crossref ' + q(query) + ' ' + rows)
      const j = parseResult(res)
      if (!j || !j.ok) return { ok: false, error: 'Crossref 检索失败: ' + String(res.stderr || res.stdout || '').slice(0, 400) }
      return { ok: true, items: j.items || [] }
    }

    async function handleLitVerify(args) {
      const refs = args.references
      if (!Array.isArray(refs) || !refs.length) return { ok: false, error: '缺少 references 数组' }
      const res = await runPyJson('lit-verify', refs)
      const j = parseResult(res)
      if (!j || !j.ok) return { ok: false, error: '核查失败: ' + String(res.stderr || res.stdout || '').slice(0, 400) }
      return { ok: true, results: j.results || [] }
    }

    ctx.effect(() => harness.handle('lit-search', (a) => handleLitSearch(a)))
    ctx.effect(() => harness.handle('lit-crossref', (a) => handleLitCrossref(a)))
    ctx.effect(() => harness.handle('lit-verify', (a) => handleLitVerify(a)))

    async function ensureDirs() {
      try {
        const spec = shell.resolve({ command: 'mkdir -p ' + q(UPLOADS) + ' ' + q(OUTPUTS) + ' ' + q(ROOT + '/tmp'), workdir: base, timeoutMs: 30000, sandboxPolicy: POLICY })
        await shell.run(spec)
      } catch (e) {}
    }

    async function scanDir(dir, kind) {
      try {
        const target = await fs.resolve(dir)
        const entries = await fs.listDir(target)
        for (const e of entries) {
          if (e.type !== 'file') continue
          // 合法文件名：<u|o>_<base36>_<seq>__<原名>，例如 o_rvw001_0__报告.docx
          const m = /^([ou]_[a-z0-9]+(?:_[a-z0-9]+)?)__(.+)$/.exec(e.name)
          if (!m) continue
          const id = m[1]
          if (files.has(id)) continue
          files.set(id, {
            id: id,
            name: m[2],
            kind: kind,
            path: dir + '/' + e.name,
            size: e.size || 0,
            format: fmtOf(m[2]),
            createdAt: Date.now(),
          })
        }
      } catch (e) {}
    }

    function countOf(kind) {
      let n = 0
      files.forEach((f) => { if (f.kind === kind) n++ })
      return n
    }

    ensureDirs().then(() => Promise.all([scanDir(UPLOADS, 'uploads'), scanDir(OUTPUTS, 'outputs')])).catch(() => {})

    ctx.effect(() => webServer.register({
      kind: 'prefix',
      path: '/dsh-docflow/download',
      handler: async (req, res) => {
        try {
          const tail = (req.url || '').split('?')[0].split('/').pop() || ''
          const info = files.get(tail)
          if (!info) {
            res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
            res.end('文件不存在或已过期')
            return
          }
          const target = await fs.resolve(info.path)
          let bytes
          try {
            bytes = await fs.readBytes(target, undefined, MAX_BYTES)
          } catch (e) {
            res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
            res.end('文件读取失败')
            return
          }
          res.writeHead(200, {
            'Content-Type': MIME[info.format] || 'application/octet-stream',
            'Content-Length': String(bytes.length),
            'Content-Disposition': 'attachment; filename="download.' + info.format + '"; filename*=UTF-8\'\'' + pct(info.name),
            'Cache-Control': 'no-store',
          })
          res.end(bytes)
        } catch (e) {
          try {
            res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' })
            res.end('服务器错误')
          } catch (e2) {}
        }
      },
    }))

    async function handleStatus() {
      await ensureDirs()
      await scanDir(UPLOADS, 'uploads')
      await scanDir(OUTPUTS, 'outputs')
      let engineReady = false
      try {
        const st = await fs.stat(await fs.resolve(ENGINE))
        engineReady = !!(st && st.type === 'file')
      } catch (e) {}
      return {
        ok: true,
        engineReady: engineReady,
        root: ROOT,
        downloadBase: urlOf(''),
        counts: { uploads: countOf('uploads'), outputs: countOf('outputs') },
      }
    }

    async function handleUpload(args) {
      const name = sanitize(args && args.name)
      const b64 = String((args && args.dataB64) || '')
      if (!b64) return { ok: false, error: '未收到文件数据' }
      if (b64.length > UPLOAD_MAX_B64) return { ok: false, error: '文件过大（超过约 90MB）' }
      const id = newId('u')
      const path = UPLOADS + '/' + id + '__' + name
      // 绕开 stdin 传递的不确定性：base64 先落盘为 .b64 文件，再由 Python 解码
      const b64Path = ROOT + '/tmp/' + id + '.b64'
      try {
        await fs.writeText(await fs.resolve(b64Path), b64, undefined, undefined, POLICY)
      } catch (e) {
        return { ok: false, error: '写入临时文件失败: ' + String((e && e.message) || e) }
      }
      const res = await runPy('decode-file ' + q(b64Path) + ' ' + q(path))
      if (res.exitCode !== 0) {
        return { ok: false, error: '保存失败: ' + String(res.stderr || res.stdout || '').slice(0, 400) }
      }
      const info = { id: id, name: name, kind: 'uploads', path: path, size: 0, format: fmtOf(name), createdAt: Date.now() }
      try {
        const st = await fs.stat(await fs.resolve(path))
        info.size = (st && st.size) || 0
      } catch (e) {}
      files.set(id, info)
      let text = ''
      let chars = 0
      let detail = null
      if (info.format !== 'file' && info.format !== 'ppt') {
        const ex = await runPy('extract ' + q(path))
        const j = parseResult(ex)
        if (j && j.ok) {
          text = j.text || ''
          chars = j.chars || 0
          detail = { pages: j.pages || 0, slides: j.slides || 0, paragraphs: j.paragraphs || 0, tables: j.tables || 0 }
        }
      }
      return { ok: true, file: pick(info), textPreview: text.slice(0, 2000), chars: chars, detail: detail }
    }

    async function handleList(args) {
      await ensureDirs()
      const kind = (args && args.kind) || 'all'
      if (kind === 'uploads' || kind === 'all') await scanDir(UPLOADS, 'uploads')
      if (kind === 'outputs' || kind === 'all') await scanDir(OUTPUTS, 'outputs')
      const all = []
      files.forEach((f) => all.push(f))
      all.sort((a, b) => b.createdAt - a.createdAt)
      return { ok: true, items: all.filter((f) => kind === 'all' || f.kind === kind).map(pick) }
    }

    async function handleParse(args) {
      const info = files.get(args && args.fileId)
      if (!info) return { ok: false, error: '文件不存在' }
      if (info.format === 'ppt') return { ok: false, error: '旧版 .ppt 无法解析，请另存为 .pptx 后重新上传' }
      const ex = await runPy('extract ' + q(info.path))
      const j = parseResult(ex)
      if (!j || !j.ok) return { ok: false, error: '解析失败: ' + String(ex.stderr || ex.stdout || '').slice(0, 400) }
      const maxChars = (args && args.maxChars) || 50000
      return {
        ok: true,
        fileId: info.id,
        name: info.name,
        text: (j.text || '').slice(0, maxChars),
        chars: j.chars || 0,
        detail: { pages: j.pages || 0, slides: j.slides || 0, paragraphs: j.paragraphs || 0, tables: j.tables || 0 },
      }
    }

    async function handleRemove(args) {
      const info = files.get(args && args.fileId)
      if (!info) return { ok: false, error: '文件不存在' }
      files.delete(info.id)
      try {
        const spec = shell.resolve({ command: 'rm -f ' + q(info.path), workdir: base, timeoutMs: 30000, sandboxPolicy: POLICY })
        await shell.run(spec)
      } catch (e) {}
      return { ok: true }
    }

    async function handleUrl(args) {
      const info = files.get(args && args.fileId)
      if (!info) return { ok: false, error: '文件不存在' }
      return { ok: true, url: urlOf(info.id), name: info.name }
    }

    ctx.effect(() => harness.handle('status', (a) => handleStatus(a)))
    ctx.effect(() => harness.handle('upload', (a) => handleUpload(a)))
    ctx.effect(() => harness.handle('list', (a) => handleList(a)))
    ctx.effect(() => harness.handle('parse', (a) => handleParse(a)))
    ctx.effect(() => harness.handle('remove', (a) => handleRemove(a)))
    ctx.effect(() => harness.handle('download-url', (a) => handleUrl(a)))

    async function doCreate(args) {
      const fmt = String(args.format || 'docx').toLowerCase()
      if (fmt === 'ppt') return { ok: false, error: '不支持旧版 .ppt 输出，请使用 pptx' }
      const baseName = sanitize(args.outputName || ((args.title || '文档') + '.' + fmt))
      const finalName = /\.(docx|pptx|pdf|md|txt)$/.test(baseName) ? baseName : baseName + '.' + fmt
      const id = newId('o')
      const path = OUTPUTS + '/' + id + '__' + finalName
      const res = await runPySpec('create', fmt, path, null, {
        title: args.title || '',
        subtitle: args.subtitle || '',
        author: args.author || '',
        date: args.date || '',
        theme: args.theme || 'blue',
        content: args.content || '',
        sections: args.sections,
      })
      if (res.exitCode !== 0) {
        return { ok: false, error: '生成失败: ' + String(res.stderr || res.stdout || '').slice(0, 500) }
      }
      const info = { id: id, name: finalName, kind: 'outputs', path: path, size: 0, format: fmt, createdAt: Date.now() }
      try {
        const st = await fs.stat(await fs.resolve(path))
        info.size = (st && st.size) || 0
      } catch (e) {}
      files.set(id, info)
      return {
        ok: true,
        value: { fileId: id, fileName: finalName, format: fmt, size: info.size, downloadUrl: urlOf(id), message: '生成成功' },
      }
    }

    async function doEdit(args) {
      const info = files.get(args && args.sourceFileId)
      if (!info) return { ok: false, error: '找不到源文件 ' + String(args && args.sourceFileId) + '，请先用 docflow_list_documents 查看可用文件' }
      let fmt = String(args.format || info.format).toLowerCase()
      if (fmt === 'markdown') fmt = 'md'
      if (fmt === 'ppt') return { ok: false, error: '旧版 .ppt 无法编辑，请另存为 .pptx 后重新上传' }
      if (['docx', 'pptx', 'pdf', 'md', 'txt'].indexOf(fmt) < 0) return { ok: false, error: '不支持的格式: ' + fmt }
      const base = String(info.name).replace(/\.[^.]+$/, '') || '文档'
      const outName = sanitize(args.outputName || (base + '_修改.' + fmt))
      const finalName = /\.(docx|pptx|pdf|md|txt)$/.test(outName) ? outName : outName + '.' + fmt
      const id = newId('o')
      const path = OUTPUTS + '/' + id + '__' + finalName
      const spec = { theme: 'blue', ops: args.ops || [] }
      const res = await runPySpec('edit', fmt, path, info.path, spec)
      if (res.exitCode !== 0) {
        return { ok: false, error: '修改失败: ' + String(res.stderr || res.stdout || '').slice(0, 500) }
      }
      const nfo = { id: id, name: finalName, kind: 'outputs', path: path, size: 0, format: fmt, createdAt: Date.now() }
      try {
        const st = await fs.stat(await fs.resolve(path))
        nfo.size = (st && st.size) || 0
      } catch (e) {}
      files.set(id, nfo)
      return {
        ok: true,
        value: { fileId: id, fileName: finalName, format: fmt, size: nfo.size, downloadUrl: urlOf(id), message: '修改成功' },
      }
    }

    const OUT_SCHEMA = {
      type: 'object',
      additionalProperties: true,
      properties: {
        fileId: { type: 'string' },
        fileName: { type: 'string' },
        format: { type: 'string' },
        size: { type: 'integer' },
        downloadUrl: { type: 'string' },
        message: { type: 'string' },
      },
    }

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_create_document',
      description: '根据 markdown 内容生成精美文档（docx/pptx/pdf/md）。文档含封面、主题配色、标题、列表、表格、引用、代码块、页眉页脚页码。生成后文件出现在浏览器的「文档工作流」面板并可下载。',
      parameters: {
        format: { type: 'string', enum: ['docx', 'pptx', 'pdf', 'md'], required: true, description: '输出格式：docx=Word、pptx=PPT、pdf=PDF、md=Markdown' },
        title: { type: 'string', required: true, description: '文档标题（封面主标题）' },
        subtitle: { type: 'string', description: '封面副标题' },
        author: { type: 'string', description: '作者/单位' },
        date: { type: 'string', description: '日期文字，如 2026年8月' },
        theme: { type: 'string', enum: ['blue', 'green', 'red', 'purple', 'gold', 'slate'], description: '配色主题，默认 blue' },
        content: { type: 'string', description: '正文 markdown：\\n# 一级标题 / ## 二级标题 / ### 三级标题 / 普通段落 / - 无序列表 / 1. 有序列表 / > 引用 / | 表头 | 表头 | + | --- | --- | + 数据行 / ```代码块``` / --- 分隔线' },
        outputName: { type: 'string', description: '输出文件名（可省略扩展名）' },
      },
      output: {
        schema: OUT_SCHEMA,
        render(args, value) {
          return [{ type: 'text', text: '已生成 ' + String(value.format || '').toUpperCase() + ' 文档「' + value.fileName + '」（' + kb(value.size) + '）。\\n下载：' + value.downloadUrl }]
        },
      },
      async execute(args) {
        const r = await doCreate(args)
        if (!r.ok) throw new Error(r.error)
        return r.value
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_edit_document',
      description: '修改已有的上传或生成文档：查找替换文本、改标题、追加内容（markdown）、更换主题色。输出为新文件，可下载。',
      parameters: {
        sourceFileId: { type: 'string', required: true, description: '源文件 ID（docflow_list_documents 查看）' },
        format: { type: 'string', enum: ['docx', 'pptx', 'pdf', 'md', 'txt'], description: '源文件格式，缺省自动判断' },
        ops: {
          type: 'array',
          required: true,
          description: '编辑操作列表，按顺序执行',
          items: {
            type: 'object',
            additionalProperties: true,
            properties: {
              type: { type: 'string', enum: ['replace', 'set-title', 'append', 'restyle'], required: true, description: 'replace=查找替换；set-title=改标题；append=追加内容；restyle=换主题色' },
              find: { type: 'string', description: 'replace 操作的查找文本' },
              replace: { type: 'string', description: 'replace 操作的替换文本' },
              title: { type: 'string', description: 'set-title 操作的新标题' },
              content: { type: 'string', description: 'append 操作追加的 markdown 内容' },
              accent: { type: 'string', description: 'restyle 操作的新主题色，如 #1F6FB2' },
            },
          },
        },
        outputName: { type: 'string', description: '输出文件名（可省略扩展名）' },
      },
      output: {
        schema: OUT_SCHEMA,
        render(args, value) {
          return [{ type: 'text', text: '已修改并生成新文档「' + value.fileName + '」（' + kb(value.size) + '）。\\n下载：' + value.downloadUrl }]
        },
      },
      async execute(args) {
        const r = await doEdit(args)
        if (!r.ok) throw new Error(r.error)
        return r.value
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_list_documents',
      description: '列出文档工作流中已上传和已生成的所有文件（含下载地址）。',
      parameters: {
        kind: { type: 'string', enum: ['uploads', 'outputs', 'all'], description: '列出范围，默认 all' },
      },
      output: {
        schema: { type: 'object', additionalProperties: true, properties: { items: { type: 'array', items: { type: 'json' } } } },
        render(args, value) {
          const items = value.items || []
          const lines = items.map((i) => (i.kind === 'outputs' ? '[生成] ' : '[上传] ') + i.name + ' (' + i.format + ', ' + kb(i.size) + ')\\n  下载: ' + i.downloadUrl)
          return [{ type: 'text', text: '共 ' + items.length + ' 个文件：\\n' + (lines.join('\\n') || '（空）') }]
        },
      },
      async execute(args) {
        const r = await handleList(args || {})
        if (!r.ok) throw new Error(r.error)
        return { items: r.items }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_parse_document',
      description: '提取上传/生成文档的纯文本内容（docx/pdf/pptx/txt/md），用于理解源文档后创建或修改。',
      parameters: {
        fileId: { type: 'string', required: true, description: '文件 ID' },
        maxChars: { type: 'integer', description: '最多返回字符数，默认 50000' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            fileId: { type: 'string' },
            name: { type: 'string' },
            text: { type: 'string' },
            chars: { type: 'integer' },
            detail: { type: 'json' },
          },
        },
        render(args, value) {
          return [{ type: 'text', text: '「' + value.name + '」共 ' + value.chars + ' 字' + (value.detail ? '（' + JSON.stringify(value.detail) + '）' : '') + '，内容见调用结果。' }]
        },
      },
      async execute(args) {
        const r = await handleParse(args)
        if (!r.ok) throw new Error(r.error)
        return { fileId: r.fileId, name: r.name, text: r.text, chars: r.chars, detail: r.detail }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_export_document',
      description: '格式转换：把已有文档内容提取后重新排版为另一种格式（docx/pptx/pdf）。',
      parameters: {
        fileId: { type: 'string', required: true, description: '源文件 ID' },
        format: { type: 'string', enum: ['docx', 'pptx', 'pdf'], required: true, description: '目标格式' },
        outputName: { type: 'string', description: '输出文件名（可省略扩展名）' },
      },
      output: {
        schema: OUT_SCHEMA,
        render(args, value) {
          return [{ type: 'text', text: '已转换为 ' + String(value.format || '').toUpperCase() + '：「' + value.fileName + '」（' + kb(value.size) + '）。\\n下载：' + value.downloadUrl }]
        },
      },
      async execute(args) {
        const info = files.get(args && args.fileId)
        if (!info) throw new Error('找不到文件 ' + String(args && args.fileId) + '，请先用 docflow_list_documents 查看')
        const fmt = String(args.format || '').toLowerCase()
        if (['docx', 'pptx', 'pdf'].indexOf(fmt) < 0) throw new Error('目标格式仅支持 docx/pptx/pdf')
        if (info.format === 'ppt') throw new Error('旧版 .ppt 无法读取，请另存为 .pptx 后重新上传')
        const ex = await runPy('extract ' + q(info.path))
        const j = parseResult(ex)
        if (!j || !j.ok) throw new Error('无法读取源文件内容: ' + String(ex.stderr || ex.stdout || '').slice(0, 300))
        const base = String(info.name).replace(/\.[^.]+$/, '') || '文档'
        const createArgs = {
          format: fmt,
          title: base,
          content: (j.text || '').slice(0, 200000),
          outputName: args.outputName,
        }
        const r = await doCreate(createArgs)
        if (!r.ok) throw new Error(r.error)
        return r.value
      },
    })))

    // ---------- 文献工具 ----------
    const LIT_SCHEMA = {
      type: 'object',
      additionalProperties: true,
      properties: {
        ok: { type: 'boolean' },
        count: { type: 'integer' },
        items: { type: 'array', items: { type: 'json' } },
        results: { type: 'array', items: { type: 'json' } },
        error: { type: 'string' },
      },
    }

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_literature_search',
      description: '从真实来源（PubMed/Medline，经 NCBI E-utilities 官方 API）检索医学文献，返回带 PMID、作者、期刊、年卷期页、DOI、摘要及 GB/T 7714-2015 顺序编码制引文格式的结构化条目，用于撰写/审阅论文参考文献。',
      parameters: {
        term: { type: 'string', required: true, description: 'PubMed 检索式，如 oral lichen planus corticosteroid randomized（支持 AND/OR/引号精确短语）' },
        maxResults: { type: 'integer', description: '最多返回条数，默认 8，上限 20' },
      },
      output: {
        schema: LIT_SCHEMA,
        render(args, value) {
          const items = value.items || []
          const lines = items.map((it, i) => '[' + (i + 1) + '] ' + it.citation + (it.abstract ? '\n    摘要: ' + it.abstract.slice(0, 200) : ''))
          return [{ type: 'text', text: 'PubMed 命中 ' + (value.count != null ? value.count : items.length) + ' 条，返回 ' + items.length + ' 条：\n' + (lines.join('\n') || '（无结果）') }]
        },
      },
      async execute(args) {
        const r = await handleLitSearch(args)
        if (!r.ok) throw new Error(r.error)
        return { ok: true, count: r.count, items: r.items }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_literature_crossref',
      description: '通过 Crossref 官方 API（DOI 权威注册库）检索文献，用于补充 PubMed 未收录的文献（含中文期刊、会议论文、专著章节），返回带 DOI 与 GB/T 7714 引文格式的条目。',
      parameters: {
        query: { type: 'string', required: true, description: '检索词（标题/作者/期刊）' },
        maxResults: { type: 'integer', description: '最多返回条数，默认 5，上限 10' },
      },
      output: {
        schema: LIT_SCHEMA,
        render(args, value) {
          const items = value.items || []
          const lines = items.map((it, i) => '[' + (i + 1) + '] ' + it.citation)
          return [{ type: 'text', text: 'Crossref 返回 ' + items.length + ' 条：\n' + (lines.join('\n') || '（无结果）') }]
        },
      },
      async execute(args) {
        const r = await handleLitCrossref(args)
        if (!r.ok) throw new Error(r.error)
        return { ok: true, items: r.items }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_literature_verify',
      description: '核查用户提供的引文真实性：逐条与 PubMed（标题/PMID）和 Crossref（DOI/标题）官方数据比对，返回 verified 真伪结论、匹配到的真实元数据与正确的 GB/T 7714-2015 引文格式，防止引用不存在的文献。',
      parameters: {
        references: {
          type: 'array',
          required: true,
          description: '待核查引文列表，每项可含 title/authors/year/doi/pmid 任一字段',
          items: {
            type: 'object',
            additionalProperties: true,
            properties: {
              title: { type: 'string', description: '文献标题' },
              authors: { type: 'array', items: { type: 'string' }, description: '作者列表' },
              year: { type: 'string', description: '发表年份' },
              doi: { type: 'string', description: 'DOI' },
              pmid: { type: 'string', description: 'PubMed ID' },
            },
          },
        },
      },
      output: {
        schema: LIT_SCHEMA,
        render(args, value) {
          const results = value.results || []
          const lines = results.map((r, i) => {
            const head = r.input && (r.input.title || r.input.doi || r.input.pmid) ? (r.input.title || r.input.doi || r.input.pmid) : ('引文' + (i + 1))
            return '[' + (i + 1) + '] ' + head + ' → ' + (r.verified ? '✅ 真实' : '❌ 未核实') + '（' + (r.notes || []).join('；') + '）' + (r.matched && r.matched.citation ? '\n    正确格式: ' + r.matched.citation : '')
          })
          return [{ type: 'text', text: '核查 ' + results.length + ' 条：\n' + (lines.join('\n') || '（无结果）') }]
        },
      },
      async execute(args) {
        const r = await handleLitVerify(args)
        if (!r.ok) throw new Error(r.error)
        return { ok: true, results: r.results }
      },
    })))

    console.log('docflow 就绪: ' + ROOT)
  },
}
