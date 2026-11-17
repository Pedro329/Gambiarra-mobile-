package com.gambiarra.infinite

import android.Manifest
import android.content.*
import android.graphics.*
import android.os.*
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject

class MainActivity : AppCompatActivity() {
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
            setPadding(36, 48, 36, 36)
        }
        val title = TextView(this).apply {
            text = "GAMBIARRA INFINITE"
            textSize = 22f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#B4A0FF"))
        }
        txtStatus = TextView(this).apply {
            text = "Status: Parado"
            textSize = 15f
            setTextColor(Color.WHITE)
            setPadding(0, 12, 0, 12)
        }
        txtInfo = TextView(this).apply {
            text = "Carregando..."
            textSize = 13f
            setTextColor(Color.parseColor("#C8C8E6"))
            setPadding(0, 0, 0, 20)
        }
        val btnStart = Button(this).apply {
            text = "Iniciar Servidor (Segundo Plano)"
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
            text = "Copiar URL (http://127.0.0.1:8080/v1)"
            setOnClickListener { copiar("http://127.0.0.1:8080/v1", "URL copiada") }
        }
        val btnCopyKey = Button(this).apply {
            text = "Copiar API Key Local"
            setOnClickListener { copiar(lastLocalKey, "Key local copiada") }
        }
        val btnFarmOne = Button(this).apply {
            text = "Farmar 1 Key Agora"
            setOnClickListener {
                Toast.makeText(this@MainActivity, "Farmando key...", Toast.LENGTH_SHORT).show()
                Thread { Python.getInstance().getModule("android_bridge").callAttr("farmar_uma", baseDir) }.start()
            }
        }
        val btnAutoFarm = Button(this).apply {
            text = "Ligar Auto-Farm (Loop)"
            setOnClickListener {
                autoFarm = !autoFarm
                text = if (autoFarm) "Parar Auto-Farm" else "Ligar Auto-Farm (Loop)"
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
        txtLogs = TextView(this).apply {
            text = "Logs prontos.\n"
            textSize = 11f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor("#78FFB4"))
            setBackgroundColor(Color.parseColor("#08080D"))
            setPadding(20, 20, 20, 20)
        }
        val scroll = ScrollView(this).apply { addView(txtLogs) }
        listOf(title, txtStatus, txtInfo, btnStart, btnStop, btnCopyUrl, btnCopyKey, btnFarmOne, btnAutoFarm).forEach { root.addView(it) }
        root.addView(scroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
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
