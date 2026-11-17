package com.gambiarra.infinite

import android.app.*
import android.content.*
import android.content.pm.ServiceInfo
import android.os.*
import androidx.core.app.NotificationCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

class GambiarraService : Service() {
    companion object {
        const val ACTION_START = "START"
        const val ACTION_STOP = "STOP"
        private const val CHANNEL_ID = "gambiarra_hub"

        fun prepareFiles(context: Context): String {
            val dest = File(context.filesDir, "gambiarra")
            if (!dest.exists()) dest.mkdirs()
            copyAssetDir(context, "gambiarra", dest)
            return dest.absolutePath
        }

        private fun copyAssetDir(context: Context, assetPath: String, destDir: File) {
            val list = context.assets.list(assetPath) ?: return
            if (list.isEmpty()) {
                if (destDir.exists() && destDir.parentFile?.name == "dados") return
                context.assets.open(assetPath).use { input ->
                    destDir.outputStream().use { output -> input.copyTo(output) }
                }
            } else {
                if (!destDir.exists()) destDir.mkdirs()
                for (child in list) copyAssetDir(context, "$assetPath/$child", File(destDir, child))
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            if (Python.isStarted()) Python.getInstance().getModule("android_bridge").callAttr("parar_servidor")
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL_ID, "Servidor Gambiarra", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Gambiarra Infinite")
            .setContentText("Hub API rodando em http://127.0.0.1:8080/v1")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(1, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(1, notif)
        }
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
        val baseDir = prepareFiles(this)
        Thread { Python.getInstance().getModule("android_bridge").callAttr("iniciar_servidor", baseDir) }.start()
        return START_STICKY
    }
}
