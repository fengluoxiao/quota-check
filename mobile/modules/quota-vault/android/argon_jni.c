#include <jni.h>
#include <stdlib.h>
#include <string.h>
#include "../ios/QuotaVaultC.h"
JNIEXPORT jbyteArray JNICALL Java_expo_modules_quotavault_QuotaVaultModule_derive(JNIEnv *env, jobject instance, jbyteArray password, jbyteArray salt) {
  jsize pn = (*env)->GetArrayLength(env,password), sn=(*env)->GetArrayLength(env,salt);
  jbyte *p=(*env)->GetByteArrayElements(env,password,NULL), *s=(*env)->GetByteArrayElements(env,salt,NULL);
  unsigned char result[32]; int code=qc_argon2id((unsigned char*)p,pn,(unsigned char*)s,sn,result,32);
  (*env)->ReleaseByteArrayElements(env,password,p,JNI_ABORT);(*env)->ReleaseByteArrayElements(env,salt,s,JNI_ABORT);
  if(code!=0){(*env)->ThrowNew(env,(*env)->FindClass(env,"java/lang/IllegalStateException"),"Argon2 derivation failed");return NULL;}
  jbyteArray out=(*env)->NewByteArray(env,32);(*env)->SetByteArrayRegion(env,out,0,32,(jbyte*)result);memset(result,0,32);return out;
}
