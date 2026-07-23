from modules.scraper import get_latest_bulletin

def run_test():
    print("========================================")
    print(" INICIANDO PRUEBA DEL SCRAPER (IGEPN)   ")
    print("========================================")
    
    volcano_test = "Reventador"
    
    file_path, file_name, source_url = get_latest_bulletin(volcano_test)

    print("\n========================================")
    print(" RESULTADOS DE LA PRUEBA                ")
    print("========================================")

    if file_path and file_name:
        print("[+] Prueba Exitosa!")
        print(f"[+] Nombre del archivo: {file_name}")
        print(f"[+] Ruta completa: {file_path}")
        print(f"[+] URL de origen: {source_url}")
    else:
        print("[-] La prueba falló. Revisa los errores en la consola.")
    print("========================================\n")

if __name__ == "__main__":
    run_test()
