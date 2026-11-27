#include "EffectGDRLairClose.h"

#include <cstdio>

#include "GCSystemMessage.h"
#include "GDRLairManager.h"
#include "ZoneGroupManager.h"

void EffectGDRLairClose::affect() {
    setNextTime(600);

    char msg[200];
    sprintf(msg, "GDR Lair closes in %d min.", m_MinutesCount);
    GCSystemMessage gcSM;
    gcSM.setMessage(msg);
    g_pZoneGroupManager->broadcast(&gcSM);
    m_MinutesCount--;
}

void EffectGDRLairClose::unaffect() {
    __BEGIN_TRY

    cout << "Closing the Gilles de Rais lair." << endl;
    GDRLairManager::Instance().close();

    GCSystemMessage gcSM;
    gcSM.setMessage("GDR Lair closed.");
    g_pZoneGroupManager->broadcast(&gcSM);

    __END_CATCH
}
