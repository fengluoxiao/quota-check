package expo.modules.quotavault

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import android.util.Base64
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

class QuotaVaultModule : Module() {
  companion object { init { System.loadLibrary("quotaargon") } }
  private external fun derive(password: ByteArray, salt: ByteArray): ByteArray
  private val random = SecureRandom()
  private val magic = byteArrayOf(83,81,86,65,85,76,84,0)
  private fun bytes(n: Int) = ByteArray(n).also { random.nextBytes(it) }
  private fun b64(data: ByteArray) = Base64.encodeToString(data,Base64.NO_WRAP)
  private fun decode(s: String) = Base64.decode(s,Base64.NO_WRAP)
  private fun key(mode: Int, secret: String, salt: ByteArray): ByteArray {
    if (mode==2) return decode(secret).also { require(it.size==32) { "设备密钥无效。" } }
    require(mode==1 && secret.codePointCount(0,secret.length) in 12..1024) { "文件密码需要 12 至 1024 个字符。" }
    return derive(secret.toByteArray(Charsets.UTF_8),salt)
  }
  private fun storage(): File = File(requireNotNull(appContext.reactContext).noBackupFilesDir,"quota-connections.sqv")
  override fun definition() = ModuleDefinition {
    Name("QuotaVault")
    Function("sha256") { text: String ->
      require(text.toByteArray(Charsets.UTF_8).size <= 2_000_000)
      java.security.MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it.toInt() and 255) }
    }
    Function("hmacSHA256") { keyHex: String, text: String ->
      require(keyHex.length in 2..65536 && keyHex.length % 2 == 0 && keyHex.matches(Regex("[0-9a-fA-F]+")))
      require(text.toByteArray(Charsets.UTF_8).size <= 2_000_000)
      val key = keyHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
      val mac = javax.crypto.Mac.getInstance("HmacSHA256")
      mac.init(SecretKeySpec(key, "HmacSHA256"))
      mac.doFinal(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it.toInt() and 255) }
    }
    Function("generateKey") { b64(bytes(32)) }
    AsyncFunction("seal") { plain: String, mode: Int, secret: String ->
      val data=plain.toByteArray(Charsets.UTF_8); require(data.size<=1024*1024 && mode in 1..2) { "配置大小或格式无效。" }
      val salt=bytes(16);val nonce=bytes(12)
      val header=ByteBuffer.allocate(46).order(ByteOrder.BIG_ENDIAN).put(magic).put(1.toByte()).put(mode.toByte()).putInt(0).put(salt).put(nonce).putInt(data.size+16).array()
      val cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,SecretKeySpec(key(mode,secret,salt),"AES"),GCMParameterSpec(128,nonce));cipher.updateAAD(header)
      b64(header+cipher.doFinal(data))
    }
    AsyncFunction("open") { blob: String, secret: String ->
      val data=decode(blob);require(data.size in 62..(2*1024*1024) && data.copyOfRange(0,8).contentEquals(magic)) { "连接文件无效。" }
      val mode=data[9].toInt();require(mode!=0) { "此文件绑定 Windows 用户，请先另存为跨电脑文件。" }
      val h=ByteBuffer.wrap(data).order(ByteOrder.BIG_ENDIAN)
      require(data[8].toInt()==1 && mode in 1..2 && h.getInt(10)==0 && h.getInt(42)>=16 && h.getInt(42)+46==data.size) { "连接文件格式无效。" }
      val cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,SecretKeySpec(key(mode,secret,data.copyOfRange(14,30)),"AES"),GCMParameterSpec(128,data.copyOfRange(30,42)));cipher.updateAAD(data.copyOfRange(0,46))
      try { String(cipher.doFinal(data.copyOfRange(46,data.size)),Charsets.UTF_8) } catch (_: Exception) { throw IllegalArgumentException("文件密码不正确或文件已损坏。") }
    }
    Function("readStorage") { storage().takeIf { it.exists() }?.let { require(it.length()<=2*1024*1024);b64(it.readBytes()) } }
    AsyncFunction("writeStorage") { blob: String ->
      val data=decode(blob);require(data.size<=2*1024*1024)
      val file=storage();val temp=File(file.parentFile,file.name+".tmp");temp.outputStream().use { it.write(data);it.fd.sync() };check(temp.renameTo(file)) { "无法保存加密连接。" }
    }
    AsyncFunction("deleteStorage") { storage().takeIf { it.exists() }?.let { check(it.delete()) } }
    AsyncFunction("request") { url: String, method: String, headers: Map<String,String>, body: String? ->
      val target=URL(url);require(target.protocol in listOf("https","http") && target.userInfo==null && method in listOf("GET","POST"))
      val connection=target.openConnection() as HttpURLConnection
      try {
        connection.instanceFollowRedirects=false;connection.connectTimeout=30000;connection.readTimeout=30000;connection.requestMethod=method
        headers.forEach { (k,v)->connection.setRequestProperty(k,v) }
        if(body!=null){connection.doOutput=true;connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }}
        val status=connection.responseCode;val stream=if(status>=400)connection.errorStream else connection.inputStream
        val data=stream?.use { input -> val output=java.io.ByteArrayOutputStream();val buffer=ByteArray(8192);while(true){val n=input.read(buffer);if(n<0)break;require(output.size()+n<=8*1024*1024);output.write(buffer,0,n)};output.toByteArray() } ?: ByteArray(0)
        mapOf("status" to status,"body" to String(data,Charsets.UTF_8))
      } finally { connection.disconnect() }
    }
  }
}
