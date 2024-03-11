
from numpy import array, linspace
from utils.tutorial_utils import show_args
from qcodes.parameters import ManualParameter
from Modularize.support import Data_manager, QDmanager
from quantify_scheduler.gettables import ScheduleGettable
from quantify_core.measurement.control import MeasurementControl
from Modularize.Pulse_schedule_library import One_tone_sche, pulse_preview
from quantify_core.analysis.spectroscopy_analysis import ResonatorSpectroscopyAnalysis

def Cavity_spec(QD_agent:QDmanager,meas_ctrl:MeasurementControl,ro_bare_guess:dict,ro_span_Hz:int=15e6,n_avg:int=300,points:int=200,run:bool=True,q:str='q1',Experi_info:dict={})->dict:
    """
        Do the cavity search by the given QuantumDevice with a given target qubit q. \n
        Please fill up the initial value about measure for qubit in QuantumDevice first, like: amp, duration, integration_time and acqusition_delay! 
    """
    quantum_device = QD_agent.quantum_device
    sche_func = One_tone_sche
    qubit_info = quantum_device.get_element(q)
    analysis_result = {}
    ro_f_center = ro_bare_guess[q]
    ro_f_samples = linspace(ro_f_center-ro_span_Hz,ro_f_center+ro_span_Hz,points)
    freq = ManualParameter(name="freq", unit="Hz", label="Frequency")
    freq.batched = True
    
    spec_sched_kwargs = dict(   
        frequencies=freq,
        q=q,
        R_amp={str(q):qubit_info.measure.pulse_amp()},
        R_duration={str(q):qubit_info.measure.pulse_duration()},
        R_integration={str(q):qubit_info.measure.integration_time()},
        R_inte_delay=qubit_info.measure.acq_delay(),
        powerDep=False,
    )
    exp_kwargs= dict(sweep_F=['start '+'%E' %ro_f_samples[0],'end '+'%E' %ro_f_samples[-1]],
                     )
    
    if run:
        gettable = ScheduleGettable(
            quantum_device,
            schedule_function=sche_func, 
            schedule_kwargs=spec_sched_kwargs,
            real_imag=False,
            batched=True,
        )
        quantum_device.cfg_sched_repetitions(n_avg)
        meas_ctrl.gettables(gettable)
        meas_ctrl.settables(freq)
        meas_ctrl.setpoints(ro_f_samples)
        
        rs_ds = meas_ctrl.run("One-tone")
        analysis_result[q] = ResonatorSpectroscopyAnalysis(tuid=rs_ds.attrs["tuid"], dataset=rs_ds).run()
        # save the xarrry into netCDF
        Data_manager().save_raw_data(QD_agent=QD_agent,ds=rs_ds,qb=q,exp_type='CS')

        print(f"{q} Cavity:")
        show_args(exp_kwargs, title="One_tone_kwargs: Meas.qubit="+q)
        if Experi_info != {}:
            show_args(Experi_info(q))
        
    else:
        n_s=2 
        sweep_para= array(ro_f_samples[:n_s])
        spec_sched_kwargs['frequencies']= sweep_para.reshape(sweep_para.shape or (1,))
        pulse_preview(quantum_device,sche_func,spec_sched_kwargs)
        show_args(exp_kwargs, title="One_tone_kwargs: Meas.qubit="+q)
        if Experi_info != {}:
            show_args(Experi_info(q))
    return analysis_result


if __name__ == "__main__":
    from Modularize.support import init_meas, init_system_atte, shut_down
    from numpy import NaN
    

    # Reload the QuantumDevice or build up a new one
    QD_path = ''
    QD_agent, cluster, meas_ctrl, ic, Fctrl = init_meas(QuantumDevice_path=QD_path,dr_loc='dr2',cluster_ip='171',mode='n')
    # Set the system attenuations
    init_system_atte(QD_agent.quantum_device,list(Fctrl.keys()),ro_out_att=0)
    for i in range(6):
        getattr(cluster.module8, f"sequencer{i}").nco_prop_delay_comp_en(True)
        getattr(cluster.module8, f"sequencer{i}").nco_prop_delay_comp(50)
    
    # guess [5.72088012 5.83476623 5.90590196 6.01276471 6.1014995 ] @DR2 
    # guess [5.26014 5.35968263 5.44950299 5.52734731 5.63612974] @ DR1 Nb
    ro_bare=dict(
        q0 = 5.721e9,
        q2 = 5.83476e9,
        q4 = 5.9059e9,
        q1 = 6.01276e9,
        q3 = 6.1015e9,
    )
    
    error_log = []
    for qb in Fctrl:
        print(qb)
        qubit = QD_agent.quantum_device.get_element(qb)
        if QD_path == '':
            qubit.reset.duration(150e-6)
            qubit.measure.acq_delay(0)
            qubit.measure.pulse_amp(0.1)
            qubit.measure.pulse_duration(2e-6)
            qubit.measure.integration_time(2e-6)
        else:
            # avoid freq conflicts
            qubit.clock_freqs.readout(NaN)
        
        CS_results = Cavity_spec(QD_agent,meas_ctrl,ro_bare,q=qb,ro_span_Hz=15e6)
        if CS_results != {}:
            print(f'Cavity {qb} @ {CS_results[qb].quantities_of_interest["fr"].nominal_value} Hz')
            QD_agent.quantum_device.get_element(qb).clock_freqs.readout(CS_results[qb].quantities_of_interest["fr"].nominal_value)
        else:
            error_log.append(qb)
    if error_log != []:
        print(f"Cavity Spectroscopy error qubit: {error_log}")

    QD_agent.refresh_log("After cavity search")
    QD_agent.QD_keeper()
    print('CavitySpectro done!')
    shut_down(cluster,Fctrl)
    
