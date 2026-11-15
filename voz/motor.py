"""Ajustes de IndexTTS-2.5 para que quepa en una GPU de 6 GB ("config E").

w2v-bert en bf16 y fuera de la GPU entre usos. Copiado de nuestras pruebas de voz.
"""
import os

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch  # noqa: E402

from indextts.infer_v2_5 import IndexTTS2  # noqa: E402,F401


def reducir_w2v_bert(tts):
    """w2v-bert (600M) viene en fp32 (~2.3 GB). En bf16 ocupa la mitad y cabe en 6 GB."""
    tts.semantic_model.to(torch.bfloat16)
    torch.cuda.empty_cache()
    original = tts.get_emb

    @torch.no_grad()
    def get_emb(input_features, attention_mask):
        out = tts.semantic_model(
            input_features=input_features.to(torch.bfloat16),
            attention_mask=attention_mask,
            output_hidden_states=True,
        )
        feat = out.hidden_states[17].float()
        return (feat - tts.semantic_mean) / tts.semantic_std

    tts.get_emb = get_emb
    tts._get_emb_fp32 = original


def descargar_w2v(tts):
    """Saca w2v-bert (1.1 GB) de la GPU entre usos.

    Solo hace falta al cambiar de voz o de clip emocional; el resultado por clip se
    guarda, así que con voces fijas el modelo vive en RAM y la GPU queda libre.
    """
    interno, memo = tts.get_emb, {}

    def get_emb(input_features, attention_mask):
        clave = (tuple(input_features.shape), float(input_features.float().sum()))
        if clave not in memo:
            tts.semantic_model.to(tts.device)
            memo[clave] = interno(input_features, attention_mask)
            tts.semantic_model.to("cpu")
            torch.cuda.empty_cache()
        return memo[clave]

    tts.get_emb = get_emb
    tts.semantic_model.to("cpu")
    torch.cuda.empty_cache()
