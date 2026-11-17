package com.gambiarra.infinite

import android.Manifest
import android.app.AlertDialog
import android.content.*
import android.graphics.*
import android.os.*
import android.text.InputType
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject

class MainActivity : AppCompatActivity() {
    companion object {
        private const val REQ_IMPORT_KEYS = 202
    }

    private lateinit var txtStatus: TextView
    private lateinit var txtInfo: TextView
    private lateinit var txtLogs: TextView
    private lateinit var baseDir: String
    private var lastLocalKey = ""
    @Volatile private var autoFarm = false
    private val handler = Handler(Looper.getMainLooper())

    private val updater = object : Runnable {
        override fun run() {
            atualizarTela()
            handler.postDelayed(this, 1500)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 101)
        }
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
        baseDir = GambiarraService.prepareFiles(this)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F0F17"))
            setPadding(32, 42, 32, 32)
        }
        val title = TextView(this).apply {
            text = "GAMBIARRA INFINITE v1.2"
            textSize = 21f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#B4A0FF"))
        }
        txtStatus = TextView(this).apply {
            text = "Status: Parado"
            textSize = 15f
            setTextColor(Color.WHITE)
            setPadding(0, 10, 0, 8)
        }
        txtInfo = TextView(this).apply {
            text = "Carregando..."
            textSize = 13f
            setTextColor(Color.parseColor("#C8C8E6"))
            setPadding(0, 0, 0, 16)
        }

        val btnStart = Button(this).apply {
            text = "Iniciar Servidor"
            setOnClickListener {
                val i = Intent(this@MainActivity, GambiarraService::class.java).apply { action = GambiarraService.ACTION_START }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i) else startService(i)
            }
        }
        val btnStop = Button(this).apply {
            text = "Parar Servidor"
            setOnClickListener {
                startService(Intent(this@MainActivity, GambiarraService::class.java).apply { action = GambiarraService.ACTION_STOP })
            }
        }
        val btnCopyUrl = Button(this).apply {
            text = "Copiar URL"
            setOnClickListener { copiar("http://127.0.0.1:8080/v1", "URL copiada") }
        }
        val btnCopyKey = Button(this).apply {
            text = "Copiar Key Local"
            setOnClickListener { copiar(lastLocalKey, "Key local copiada") }
        }
        val btnFarmOne = Button(this).apply {
            text = "Farmar 1 Key"
            setOnClickListener {
                Toast.makeText(this@MainActivity, "Farmando key...", Toast.LENGTH_SHORT).show()
                Thread { Python.getInstance().getModule("android_bridge").callAttr("farmar_uma", baseDir) }.start()
            }
        }
        val btnAutoFarm = Button(this).apply {
            text = "Ligar Auto-Farm"
            setOnClickListener {
                autoFarm = !autoFarm
                text = if (autoFarm) "Parar Auto-Farm" else "Ligar Auto-Farm"
                if (autoFarm) {
                    Thread {
                        val py = Python.getInstance().getModule("android_bridge")
                        while (autoFarm) {
                            py.callAttr("farmar_uma", baseDir)
                            Thread.sleep(3000)
                        }
                    }.start()
                }
            }
        }
        val btnConfig = Button(this).apply {
            text = "Configurações (Provider / URL e Key)"
            setOnClickListener { abrirConfiguracoes() }
        }

        txtLogs = TextView(this).apply {
            text = "Logs prontos.\n"
            textSize = 11f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor("#78FFB4"))
            setBackgroundColor(Color.parseColor("#08080D"))
            setPadding(20, 20, 20, 20)
        }
        val scroll = ScrollView(this).apply { addView(txtLogs) }

        root.addView(title)
        root.addView(txtStatus)
        root.addView(txtInfo)
        root.addView(linhaDupla(btnStart, btnStop))
        root.addView(linhaDupla(btnCopyUrl, btnCopyKey))
        root.addView(linhaDupla(btnFarmOne, btnAutoFarm))
        root.addView(btnConfig)
        root.addView(scroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
    }

    private fun linhaDupla(b1: Button, b2: Button): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            addView(b1, lp)
            addView(b2, lp)
        }
    }

    private fun abrirConfiguracoes() {
        try {
            val raw = Python.getInstance().getModule("android_bridge").callAttr("listar_providers_json", baseDir).toString()
            val obj = JSONObject(raw)
            val arr = obj.getJSONArray("providers")
            val nomes = mutableListOf<String>()
            val titulos = mutableListOf<String>()
            var idxAtivo = 0
            for (i in 0 until arr.length()) {
                val item = arr.getJSONObject(i)
                nomes.add(item.getString("nome"))
                val nota = item.optString("nota", "")
                titulos.add(if (nota.isNotEmpty()) "${item.getString("titulo")} ($nota)" else item.getString("titulo"))
                if (item.optBoolean("ativo", false)) idxAtivo = i
            }

            val box = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(44, 28, 44, 16)
            }

            val lblProv = TextView(this).apply {
                text = "1. Provider ativo:"
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
            }
            val spinner = Spinner(this).apply {
                adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, titulos)
                setSelection(idxAtivo)
            }
            val btnSalvarProv = Button(this).apply {
                text = "Aplicar Provider Selecionado"
                setOnClickListener {
                    val escolhido = nomes[spinner.selectedItemPosition]
                    val res = JSONObject(Python.getInstance().getModule("android_bridge").callAttr("trocar_provider", baseDir, escolhido).toString())
                    if (res.optBoolean("ok")) {
                        Toast.makeText(this@MainActivity, "Provider: ${res.optString("titulo")}", Toast.LENGTH_SHORT).show()
                        atualizarTela()
                    }
                }
            }

            val lblManual = TextView(this).apply {
                text = "\n2. Adicionar URL + Key na hora:"
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
            }
            val edtNome = EditText(this).apply {
                hint = "Nome (opcional, ex: Roteia AI)"
                inputType = InputType.TYPE_CLASS_TEXT
                isSingleLine = true
            }
            val edtUrl = EditText(this).apply {
                hint = "Base URL (ex: https://api.roteia.ai/v1)"
                inputType = InputType.TYPE_TEXT_VARIATION_URI
                isSingleLine = true
            }
            val edtKey = EditText(this).apply {
                hint = "API Key (ex: rt-live-... ou sk-...)"
                inputType = InputType.TYPE_CLASS_TEXT
                isSingleLine = true
            }

            var dialogRef: AlertDialog? = null

            val btnSalvarManual = Button(this).apply {
                text = "Salvar e Ativar Provider"
                setOnClickListener {
                    val nomeTxt = edtNome.text.toString().trim()
                    val urlTxt = edtUrl.text.toString().trim()
                    val keyTxt = edtKey.text.toString().trim()
                    if (urlTxt.isEmpty() || keyTxt.isEmpty()) {
                        Toast.makeText(this@MainActivity, "Preencha a URL e a API Key", Toast.LENGTH_SHORT).show()
                        return@setOnClickListener
                    }
                    Thread {
                        val rawRes = Python.getInstance()
                            .getModule("android_bridge")
                            .callAttr("adicionar_custom_manual", baseDir, nomeTxt, urlTxt, keyTxt, "")
                            .toString()
                        val res = JSONObject(rawRes)
                        runOnUiThread {
                            if (res.optBoolean("ok")) {
                                Toast.makeText(this@MainActivity, "Ativado: ${res.optString("titulo")}", Toast.LENGTH_LONG).show()
                                atualizarTela()
                                dialogRef?.dismiss()
                            } else {
                                Toast.makeText(this@MainActivity, "Erro: ${res.optString("erro")}", Toast.LENGTH_LONG).show()
                            }
                        }
                    }.start()
                }
            }

            val lblKeys = TextView(this).apply {
                text = "\n3. Importar Arquivo ou Recarregar:"
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
            }
            val btnImportar = Button(this).apply {
                text = "Importar Arquivo (.json)"
                setOnClickListener {
                    val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                    }
                    startActivityForResult(intent, REQ_IMPORT_KEYS)
                }
            }
            val btnReviver = Button(this).apply {
                text = "Reativar Keys Mortas / Recarregar Pool"
                setOnClickListener {
                    val total = Python.getInstance().getModule("android_bridge").callAttr("reviver_keys", baseDir).toInt()
                    Toast.makeText(this@MainActivity, "Pool recarregado: $total keys", Toast.LENGTH_SHORT).show()
                    atualizarTela()
                }
            }

            box.addView(lblProv)
            box.addView(spinner)
            box.addView(btnSalvarProv)
            box.addView(lblManual)
            box.addView(edtNome)
            box.addView(edtUrl)
            box.addView(edtKey)
            box.addView(btnSalvarManual)
            box.addView(lblKeys)
            box.addView(btnImportar)
            box.addView(btnReviver)

            val dialogScroll = ScrollView(this).apply { addView(box) }

            dialogRef = AlertDialog.Builder(this)
                .setTitle("Configurações")
                .setView(dialogScroll)
                .setPositiveButton("Fechar", null)
                .show()
        } catch (e: Exception) {
            Toast.makeText(this, "Erro ao abrir configurações: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_IMPORT_KEYS && resultCode == RESULT_OK) {
            val uri = data?.data ?: return
            Thread {
                try {
                    val texto = contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() } ?: ""
                    val rawRes = Python.getInstance().getModule("android_bridge").callAttr("importar_keys_json", baseDir, texto).toString()
                    val res = JSONObject(rawRes)
                    runOnUiThread {
                        if (res.optBoolean("ok")) {
                            Toast.makeText(this, "+${res.optInt("novas")} keys importadas! Total: ${res.optInt("total")}", Toast.LENGTH_LONG).show()
                            atualizarTela()
                        } else {
                            Toast.makeText(this, "Erro: ${res.optString("erro")}", Toast.LENGTH_LONG).show()
                        }
                    }
                } catch (e: Exception) {
                    runOnUiThread { Toast.makeText(this, "Falha ao ler arquivo: ${e.message}", Toast.LENGTH_SHORT).show() }
                }
            }.start()
        }
    }

    override fun onResume() { super.onResume(); handler.post(updater) }
    override fun onPause() { super.onPause(); handler.removeCallbacks(updater) }

    private fun atualizarTela() {
        try {
            val obj = JSONObject(Python.getInstance().getModule("android_bridge").callAttr("status_json", baseDir).toString())
            val rodando = obj.getBoolean("rodando")
            lastLocalKey = obj.getString("local_key")
            txtStatus.text = if (rodando) "Status: RODANDO (127.0.0.1:${obj.getInt("porta")})" else "Status: PARADO"
            txtStatus.setTextColor(if (rodando) Color.parseColor("#78FFB4") else Color.parseColor("#FF6E6E"))
            txtInfo.text = "Provider: ${obj.getString("provider")} | Modelos: ${obj.getInt("modelos")}\n" +
                "Keys: ${obj.getInt("keys_uteis")}/${obj.getInt("keys_total")} úteis | Chamadas: ${obj.getInt("requests")}"
            val logs = obj.getString("logs")
            if (logs.isNotEmpty()) txtLogs.text = logs
        } catch (_: Exception) {}
    }

    private fun copiar(texto: String, aviso: String) {
        if (texto.isBlank()) return
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("gambiarra", texto))
        Toast.makeText(this, aviso, Toast.LENGTH_SHORT).show()
    }
}
