package org.supracraft.microscope;

import java.lang.instrument.Instrumentation;
import java.util.LinkedHashMap;
import java.util.Map;

public final class Agent {
    private Agent() {}

    public static void premain(String agentArgs, Instrumentation instrumentation) {
        Map<String,String> args=parse(agentArgs);
        String adapter=value(args,"adapter","legacy-1.8.8");
        if (!"legacy-1.8.8".equals(adapter)) {
            System.err.println("SupraCraft causal microscope: unsupported adapter "+adapter);
            Runtime.getRuntime().halt(73);
        }
        String out=value(args,"out","supracraft-causal-trace.jsonl");
        TraceRuntime.start("legacy-1.8.8-mcp918",out);
        instrumentation.addTransformer(new Legacy188Transformer(),false);
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override public void run() { TraceRuntime.close(); }
        },"supracraft-causal-microscope-shutdown"));
    }

    private static String value(Map<String,String> args,String key,String fallback) {
        String value=args.get(key);
        return value==null || value.isEmpty() ? fallback : value;
    }

    private static Map<String,String> parse(String text) {
        Map<String,String> out=new LinkedHashMap<String,String>();
        if (text==null || text.trim().isEmpty()) return out;
        for (String token:text.split(",")) {
            int p=token.indexOf('=');
            if (p<=0) continue;
            out.put(token.substring(0,p).trim(),token.substring(p+1).trim());
        }
        return out;
    }
}
